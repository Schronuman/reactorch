from multiprocessing import Pool
from time import perf_counter

import cantera as ct
import matplotlib.pyplot as plt
import numpy as np
import torch

import reactorch as rt

cpu = torch.device('cpu')

cuda = torch.device('cuda:0')

device = cpu

mech_yaml = '../data/gri30.yaml'
composition = "CH4:0.5, O2:1.0, N2:3.76"

sol = rt.Solution(mech_yaml=mech_yaml, device=device)

gas = sol.gas
gas.TPX = 950, 20 * ct.one_atm, composition

r = ct.IdealGasReactor(gas)
sim = ct.ReactorNet([r])

time = 0.0
t_end = 10
idt = 0
states = ct.SolutionArray(gas, extra=['t'])
T0 = gas.T

print('%10s %10s %10s %14s' % ('t [s]', 'T [K]', 'P [atm]', 'u [J/kg]'))

while sim.time < t_end:

    sim.step()

    states.append(r.thermo.state, t=time)

    if r.thermo.T > T0 + 600 and idt < 1e-10:
        idt = sim.time

    if idt > 1e-10 and sim.time > 4 * idt:
        break

print('%10.3e %10.3f %10.3f %14.6e' % (sim.time,
                                       r.T,
                                       r.thermo.P / ct.one_atm,
                                       r.thermo.u))

print('idt = {:.2e} [s] number of points {}'.format(idt, states.t.shape[0]))

TP = torch.stack((torch.Tensor(states.T), torch.Tensor(states.P)), dim=-1)
Y = torch.Tensor(states.Y)
TPY = torch.cat([TP, Y], dim=-1).to(device)

t0_start = perf_counter()

sol.set_states(TPY)

t1_stop = perf_counter()
print('sol set_states time spent {:.1e} [s]'.format(t1_stop - t0_start))


def check_rates(i):

    eps = 1e-300
    delta = 1e-3

    ratio = (states.forward_rate_constants[:, i] + eps) / \
        (sol.forward_rate_constants[:, i].detach().cpu().numpy() + eps)

    if ratio.min() < 1 - delta or ratio.max() > 1 + delta:
        print("forward constants {} {} {:.2e} {:.2e}".format(i, gas.reaction_equation(i), ratio.min(), ratio.max()))

    ratio = (states.equilibrium_constants[:, i] + eps) / \
        (sol.equilibrium_constants[:, i].detach().cpu().numpy() + eps)

    if ratio.min() < 1 - delta or ratio.max() > 1 + delta:
        print("equilibrium constants {} {} {:.2e} {:.2e}".format(i, gas.reaction_equation(i), ratio.min(), ratio.max()))

    ratio = (states.reverse_rate_constants[:, i] + eps) / \
        (sol.reverse_rate_constants[:, i].detach().cpu().numpy() + eps)

    if ratio.min() < 1 - delta or ratio.max() > 1 + delta:
        print("reverse constants {} {} {:.2e} {:.2e}".format(i, gas.reaction_equation(i), ratio.min(), ratio.max()))

    return i

with Pool(4) as p:
    print(p.map(check_rates, range(gas.n_reactions)))

t1_stop = perf_counter()
print('sol check_rates time spent {:.1e} [s]'.format(t1_stop - t0_start))
