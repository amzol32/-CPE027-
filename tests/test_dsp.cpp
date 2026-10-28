// Host-side tests for firmware/soil_dsp/dsp.h
//   g++ -std=c++17 -O2 -I firmware/soil_dsp tests/test_dsp.cpp -o build/test_dsp
//   ./build/test_dsp                       -> unit tests
//   ./build/test_dsp dump in.csv a1 w1 a2 w2 a3 w3 alpha  -> run the pipeline on a log
//        (prints t_s,m1,m2,m3,x,z,y,yma so analysis/crosscheck.py can compare with numpy)
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include "dsp.h"

static int failures = 0;
#define CHECK(cond)                                                     \
  do {                                                                  \
    if (!(cond)) { std::printf("FAIL line %d: %s\n", __LINE__, #cond); failures++; } \
  } while (0)
static bool near(float a, float b, float tol = 1e-4f) { return std::fabs(a - b) <= tol; }

static void testMedian3() {
  CHECK(dsp::median3(1, 2, 3) == 2);
  CHECK(dsp::median3(3, 2, 1) == 2);
  CHECK(dsp::median3(2, 3, 1) == 2);
  CHECK(dsp::median3(5, 5, 9) == 5);
  CHECK(dsp::median3(0, 100, 50) == 50);
  // one faulty sensor must not reach the output
  CHECK(dsp::median3(40, 41, 0) == 40);
  CHECK(dsp::median3(40, 41, 100) == 41);
}

static void testCalibration() {
  CHECK(near(dsp::toIndex(3000, 3000, 1200), 0.0f));
  CHECK(near(dsp::toIndex(1200, 3000, 1200), 100.0f));
  CHECK(near(dsp::toIndex(2100, 3000, 1200), 50.0f));
  CHECK(near(dsp::toIndex(3500, 3000, 1200), 0.0f));    // clamped
  CHECK(near(dsp::toIndex(900, 3000, 1200), 100.0f));   // clamped
  CHECK(std::isfinite(dsp::toIndex(2000, 2000, 2000))); // bad span guarded
}

static void testRunningMedian() {
  dsp::RunningMedian<5> rm;
  // impulse of 1 or 2 samples must be removed completely once window is full
  float in[]  = {10, 10, 10, 10, 10, 90, 10, 10, 10, 10, 90, 90, 10, 10, 10, 10};
  float out[16];
  for (int i = 0; i < 16; i++) out[i] = rm.update(in[i]);
  for (int i = 4; i < 16; i++) CHECK(out[i] == 10);
  // sustained step passes after a delay of 3 samples (N=5)
  dsp::RunningMedian<5> r2;
  float o;
  for (int i = 0; i < 10; i++) o = r2.update(0);
  int firstAbove = -1;
  for (int i = 0; i < 10; i++) { o = r2.update(100); if (o > 50 && firstAbove < 0) firstAbove = i; }
  CHECK(firstAbove == 2);  // 3rd step sample
}

static void testEma() {
  dsp::Ema e(0.1f);
  CHECK(near(e.update(50), 50));  // seeded with first sample
  float y = 0;
  for (int i = 0; i < 200; i++) y = e.update(80);
  CHECK(near(y, 80, 1e-2f));
  // time constant -1/ln(1-a) = 9.49 samples: step response after 10 samples ~ 1-0.9^10
  dsp::Ema s(0.1f);
  s.update(0);
  float v = 0;
  for (int i = 0; i < 10; i++) v = s.update(100);
  CHECK(near(v, 100.0f * (1.0f - std::pow(0.9f, 10)), 1e-3f));
}

static void testMovingAverage() {
  dsp::MovingAverage<10> ma;
  float y = 0;
  for (int i = 0; i < 25; i++) y = ma.update(7);
  CHECK(near(y, 7));
  // impulse of height 100 spreads to 10 per sample over M samples (not removed)
  dsp::MovingAverage<10> m2;
  for (int i = 0; i < 20; i++) m2.update(0);
  float a = m2.update(100);
  float b = m2.update(0);
  CHECK(near(a, 10) && near(b, 10));
}

static void testToggles() {
  dsp::ToggleCounter t(35.0f, 0.0f);
  float seq[] = {40, 34, 36, 34, 40, 40};
  for (float v : seq) t.update(v);
  CHECK(t.count() == 4);
  dsp::ToggleCounter h(35.0f, 4.0f);  // band 33..37 absorbs the small wiggles
  float seq2[] = {40, 36, 34.5f, 35.5f, 34.5f, 40};
  for (float v : seq2) h.update(v);
  CHECK(h.count() == 0);
}

static void testController() {
  dsp::Params p;
  p.thetaDry = 35; p.hysteresis = 8; p.thetaWet = 80;
  p.tMaxMs = 15000; p.lockoutMs = 120000; p.blankMs = 3000;
  dsp::Controller c(p);
  uint32_t t = 0;
  // OK region: pump off
  c.update(50, t, true); CHECK(!c.pump() && c.status() == dsp::Status::OK);
  // below theta_dry: pump starts
  t += 1000; c.update(30, t, true); CHECK(c.pump() && c.status() == dsp::Status::DRY);
  // inside hysteresis band (35..43): keeps running
  t += 1000; c.update(40, t, true); CHECK(c.pump());
  // reaches theta_dry + h: stops
  t += 1000; c.update(43, t, true); CHECK(!c.pump());
  // lockout: dips dry again right away, must not restart
  t += 1000; c.update(20, t, true); CHECK(!c.pump());
  t += 100000; c.update(20, t, true); CHECK(!c.pump());  // 101 s since stop < 120 s
  t += 30000; c.update(20, t, true); CHECK(c.pump());    // lockout elapsed
  // Tmax: sensor stuck dry, pump must stop after 15 s
  t += 14000; c.update(20, t, true); CHECK(c.pump());
  t += 1500;  c.update(20, t, true); CHECK(!c.pump());
  // wet alert is independent of the pump
  t += 1000; c.update(85, t, true); CHECK(c.wet() && c.status() == dsp::Status::WET && !c.pump());
  // disabled: pump forced off
  dsp::Controller d(p);
  d.update(10, 0, false); CHECK(!d.pump());
}

static void testPipelineFaultRejection() {
  // sensor 3 faults to 0 for 20 samples; the output must not move
  dsp::Pipeline<5, 10> pl(0.1f);
  dsp::PipelineOut o{};
  for (int i = 0; i < 60; i++) o = pl.update(50, 51, 50);
  for (int i = 0; i < 20; i++) o = pl.update(50, 51, 0);
  CHECK(std::fabs(o.y - 50) < 1.0f);
  // one sample spike on one sensor is removed by stage 1; moving average sees x only
  dsp::Pipeline<5, 10> p2(0.1f);
  for (int i = 0; i < 60; i++) o = p2.update(50, 50, 50);
  o = p2.update(50, 50, 100);
  CHECK(near(o.x, 50) && near(o.y, 50) && near(o.yma, 50));
}

static int dump(int argc, char** argv) {
  if (argc < 10) { std::fprintf(stderr, "usage: dump in.csv a1 w1 a2 w2 a3 w3 alpha\n"); return 2; }
  std::ifstream f(argv[2]);
  if (!f) { std::fprintf(stderr, "cannot open %s\n", argv[2]); return 2; }
  float a[3], w[3];
  for (int i = 0; i < 3; i++) { a[i] = std::atof(argv[3 + 2 * i]); w[i] = std::atof(argv[4 + 2 * i]); }
  float alpha = std::atof(argv[9]);
  dsp::Pipeline<5, 10> pl(alpha);
  std::string line;
  std::getline(f, line);  // header
  std::printf("t_s,m1,m2,m3,x,z,y,yma\n");
  while (std::getline(f, line)) {
    std::stringstream ss(line);
    std::string tok;
    float v[5] = {0, 0, 0, 0, 0};
    for (int i = 0; i < 5 && std::getline(ss, tok, ','); i++) v[i] = std::atof(tok.c_str());
    float m1 = dsp::toIndex(v[1], a[0], w[0]);
    float m2 = dsp::toIndex(v[2], a[1], w[1]);
    float m3 = dsp::toIndex(v[3], a[2], w[2]);
    dsp::PipelineOut o = pl.update(m1, m2, m3);
    std::printf("%.3f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n", v[0], o.m1, o.m2, o.m3, o.x, o.z, o.y, o.yma);
  }
  return 0;
}

int main(int argc, char** argv) {
  if (argc > 1 && std::strcmp(argv[1], "dump") == 0) return dump(argc, argv);
  testMedian3();
  testCalibration();
  testRunningMedian();
  testEma();
  testMovingAverage();
  testToggles();
  testController();
  testPipelineFaultRejection();
  if (failures) { std::printf("%d check(s) FAILED\n", failures); return 1; }
  std::printf("all dsp.h tests passed\n");
  return 0;
}
