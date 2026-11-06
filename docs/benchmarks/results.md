# Physics backend benchmark: results

Generated 2026-11-06T09:46:59+00:00 on Windows 11, AMD64 Family 25 Model 116 Stepping 1, AuthenticAMD, Python 3.12.16. Regenerate with `vw bench`. Interpretation: [README.md](README.md).

## Configs

| Label | Backend | Version | Device | Config | Analytic suite sim time |
|---|---|---|---|---|---|
| mujoco/euler/4ms | mujoco | 3.17.0 | cpu | timestep=0.004 | 0.16 s |
| mujoco/euler/2ms (default) | mujoco | 3.17.0 | cpu | timestep=0.002 | 0.24 s |
| mujoco/euler/1ms | mujoco | 3.17.0 | cpu | timestep=0.001 | 0.41 s |
| mujoco/euler/0.5ms | mujoco | 3.17.0 | cpu | timestep=0.0005 | 0.74 s |
| mujoco/implicitfast/2ms | mujoco | 3.17.0 | cpu | timestep=0.002, integrator=implicitfast | 0.25 s |
| mujoco/rk4/2ms | mujoco | 3.17.0 | cpu | timestep=0.002, integrator=RK4 | 0.33 s |
| mujoco/euler/2ms/elliptic | mujoco | 3.17.0 | cpu | timestep=0.002, cone=elliptic | 0.23 s |
| mujoco/euler/2ms/no-contacts | mujoco | 3.17.0 | cpu | timestep=0.002, record_contacts=False | 0.10 s |

## Analytic suite

Cells: measured value (relative error where the expected value is non-zero).

| Case | Metric | Expected | mujoco/euler/4ms | mujoco/euler/2ms (default) | mujoco/euler/1ms | mujoco/euler/0.5ms | mujoco/implicitfast/2ms | mujoco/rk4/2ms | mujoco/euler/2ms/elliptic | mujoco/euler/2ms/no-contacts |
|---|---|---|---|---|---|---|---|---|---|---|
| free_fall | max position error over 1 s [m] | 0 | 0.0196 | 0.0098 | 0.0049 | 0.0025 | 0.0098 | 1.33e-14 | 0.0098 | 0.0098 |
| free_fall | time to drop 1 m [s] | 0.4515 | 0.4495 (0.4%) | 0.4505 (0.2%) | 0.451 (0.1%) | 0.4513 (0.1%) | 0.4505 (0.2%) | 0.4515 (0.0%) | 0.4505 (0.2%) | 0.4505 (0.2%) |
| bounce | rebound height (e=0.0) [m] | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| bounce | rebound height (e=0.3) [m] | 0.09 | 0.1267 (40.7%) | 0.1308 (45.3%) | 0.1329 (47.7%) | 0.1283 (42.6%) | 0.1308 (45.3%) | 0.1312 (45.8%) | 0.1354 (50.4%) | 0.1308 (45.3%) |
| bounce | rebound height (e=0.6) [m] | 0.36 | 0.3789 (5.3%) | 0.3812 (5.9%) | 0.3823 (6.2%) | 0.3755 (4.3%) | 0.3812 (5.9%) | 0.3785 (5.1%) | 0.3874 (7.6%) | 0.3812 (5.9%) |
| bounce | rebound height (e=0.9) [m] | 0.81 | 0.811 (0.1%) | 0.8106 (0.1%) | 0.8109 (0.1%) | 0.8062 (0.5%) | 0.8106 (0.1%) | 0.8077 (0.3%) | 0.8143 (0.5%) | 0.8106 (0.1%) |
| slide | stopping distance (mu=0.2) [m] | 1.0194 | 1.0155 (0.4%) | 1.0174 (0.2%) | 1.0185 (0.1%) | 1.019 (0.0%) | 1.0174 (0.2%) | 1.0195 (0.0%) | 1.0175 (0.2%) | 1.0174 (0.2%) |
| slide | stopping distance (mu=0.5) [m] | 0.4077 | 0.404 (0.9%) | 0.4059 (0.4%) | 0.4073 (0.1%) | 0.4079 (0.0%) | 0.4059 (0.4%) | 0.4082 (0.1%) | 0.406 (0.4%) | 0.4059 (0.4%) |
| stack | top box drift over 3 s (5 boxes) [m] | 0 | 0.0029 | 6.52e-04 | 4.30e-04 | 4.22e-04 | 8.88e-04 | 4.38e-04 | 0.0021 | 6.52e-04 |
| stack | max penetration (5 boxes) [m] | 0 | 8.74e-04 | 2.04e-04 | 1.34e-04 | 1.34e-04 | 2.56e-04 | 1.34e-04 | 5.93e-04 | 2.04e-04 |
| collision | momentum after (e=1.0) [kg*m/s] | 1 | 1 (0.0%) | 1 (0.0%) | 1 (0.0%) | 1 (0.0%) | 1 (0.0%) | 1 (0.0%) | 1 (0.0%) | 1 (0.0%) |
| collision | v_B after (e=1.0) [m/s] | 1 | 1.0004 (0.0%) | 0.999 (0.1%) | 0.9985 (0.2%) | 0.9984 (0.2%) | 0.999 (0.1%) | 0.9983 (0.2%) | 0.999 (0.1%) | 0.999 (0.1%) |
| collision | momentum after (e=0.5) [kg*m/s] | 1 | 1 (0.0%) | 1 (0.0%) | 1 (0.0%) | 1 (0.0%) | 1 (0.0%) | 1 (0.0%) | 1 (0.0%) | 1 (0.0%) |
| collision | v_B after (e=0.5) [m/s] | 0.75 | 0.7562 (0.8%) | 0.7639 (1.9%) | 0.7676 (2.3%) | 0.7695 (2.6%) | 0.7639 (1.9%) | 0.7694 (2.6%) | 0.7686 (2.5%) | 0.7639 (1.9%) |

## Consistency vs reference (mujoco/rk4/0.25ms (reference))

Max position deviation over all bodies and frames, in meters (worst body in brackets).

| Scene | mujoco/euler/4ms | mujoco/euler/2ms (default) | mujoco/euler/1ms | mujoco/euler/0.5ms | mujoco/implicitfast/2ms | mujoco/rk4/2ms | mujoco/euler/2ms/elliptic | mujoco/euler/2ms/no-contacts |
|---|---|---|---|---|---|---|---|---|
| stack5 | 0.0027 [b4] | 4.83e-04 [b4] | 2.04e-04 [b4] | 8.36e-05 [b4] | 7.27e-04 [b3] | 2.08e-04 [b4] | 0.0018 [b4] | 4.83e-04 [b4] |
| bounce_e0.6 | 0.0109 [ball] | 0.0056 [ball] | 0.0088 [ball] | 0.0038 [ball] | 0.0056 [ball] | 0.0042 [ball] | 0.0208 [ball] | 0.0056 [ball] |
| slide_mu0.5 | 0.0057 [box] | 0.0055 [box] | 0.0026 [box] | 0.0027 [box] | 0.0055 [box] | 0.0029 [box] | 0.0021 [box] | 0.0055 [box] |
| tumble | 0.791 [b3] | 0.4443 [b3] | 0.2246 [b3] | 0.1214 [ball] | 0.4001 [b3] | 0.0669 [ball] | 0.1101 [b3] | 0.4443 [b3] |
| remove_support/baseline | 2.24e-04 [support] | 1.20e-04 [support] | 1.26e-04 [box] | 5.46e-05 [box] | 1.20e-04 [support] | 6.15e-05 [support] | 2.47e-04 [box] | 1.20e-04 [support] |
| remove_support/causal | 0.0059 [box] | 0.0024 [box] | 0.0012 [box] | 6.08e-04 [box] | 0.0024 [box] | 3.15e-04 [box] | 0.0024 [box] | 0.0024 [box] |

Simulation wall-clock per scene (s):

| Scene | mujoco/euler/4ms | mujoco/euler/2ms (default) | mujoco/euler/1ms | mujoco/euler/0.5ms | mujoco/implicitfast/2ms | mujoco/rk4/2ms | mujoco/euler/2ms/elliptic | mujoco/euler/2ms/no-contacts |
|---|---|---|---|---|---|---|---|---|
| stack5 | 0.105 | 0.173 | 0.315 | 0.573 | 0.180 | 0.230 | 0.167 | 0.049 |
| bounce_e0.6 | 0.006 | 0.007 | 0.009 | 0.012 | 0.007 | 0.011 | 0.007 | 0.006 |
| slide_mu0.5 | 0.010 | 0.011 | 0.019 | 0.035 | 0.011 | 0.017 | 0.012 | 0.005 |
| tumble | 0.062 | 0.095 | 0.160 | 0.303 | 0.097 | 0.139 | 0.095 | 0.032 |
| remove_support/baseline | 0.031 | 0.057 | 0.117 | 0.229 | 0.061 | 0.084 | 0.056 | 0.011 |
| remove_support/causal | 0.019 | 0.031 | 0.057 | 0.108 | 0.030 | 0.042 | 0.028 | 0.007 |

![Error vs wall-clock](error_vs_walltime.png)
