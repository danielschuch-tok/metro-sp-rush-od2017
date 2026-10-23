"""Ciclo diurno das viagens que usam metrô/monotrilho (OD 2017, dia útil).

Para cada janela de 15 min calcula, ponderado por FE_VIA:
  saidas       - viagens iniciadas
  chegadas     - viagens terminadas
  em_andamento - viagens em curso (peso espalhado entre saída e chegada)
Também roda bootstrap por pessoa para o horário dos picos.

Saídas: dados/processados/ciclo_metro_15min.csv, dados/processados/bootstrap_picos.txt
Limitação: o horário é o da viagem inteira (inclui a pé/ônibus), não só do trecho no metrô.
"""
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PROC = RAIZ / 'dados/processados'
B = 15                 # minutos por janela
NB = 1440 // B
N_BOOT = 200

df = pd.read_pickle(PROC / 'od2017_viagens.pkl').dropna(subset=['N_VIAG'])  # sem N_VIAG = pessoa sem viagem
modos = df[['MODO1', 'MODO2', 'MODO3', 'MODO4']]
df['metro'] = modos.isin([1, 3]).any(axis=1)   # 1 = metrô, 3 = monotrilho, em qualquer trecho
t0 = (df.H_SAIDA * 60 + df.MIN_SAIDA).to_numpy()
t1 = (df.H_CHEG * 60 + df.MIN_CHEG).to_numpy()
t1 = np.where(t1 < t0, t1 + 1440, t1)          # viagem que vira a meia-noite
df['t0'], df['t1'] = t0, t1

w = df.FE_VIA
print('viagens/dia (expandido): %.2f mi' % (w.sum() / 1e6))
print('com metrô/monotrilho: %.2f mi (n=%d)' % (w[df.metro].sum() / 1e6, df.metro.sum()))


def em_andamento(a, b, ww):
    occ = np.zeros(NB)
    for x, y, z in zip(a, b, ww):
        y = max(y, x + 1)
        for k in range(int(x // B), int((y - 1) // B) + 1):
            occ[k % NB] += z * (min(y, (k + 1) * B) - max(x, k * B)) / B
    return occ


mt = df[df.metro].reset_index(drop=True)
dep = np.bincount((mt.t0 // B).astype(int) % NB, weights=mt.FE_VIA, minlength=NB)
arr = np.bincount((mt.t1 // B).astype(int) % NB, weights=mt.FE_VIA, minlength=NB)
occ = em_andamento(mt.t0, mt.t1, mt.FE_VIA)

out = pd.DataFrame({'inicio': [f'{i * B // 60:02d}:{i * B % 60:02d}' for i in range(NB)],
                    'saidas': dep, 'chegadas': arr, 'em_andamento': occ})
out['pct_pico'] = 100 * occ / occ.max()
out.round(1).to_csv(PROC / 'ciclo_metro_15min.csv', index=False)

# bootstrap por pessoa (viagens da mesma pessoa não são independentes)
rng = np.random.default_rng(0)
idx = mt.groupby('ID_PESS').indices
pessoas = np.array(list(idx))
res = []
for _ in range(N_BOOT):
    ii = np.concatenate([idx[p] for p in rng.choice(pessoas, len(pessoas))])
    s = mt.iloc[ii]
    oc = em_andamento(s.t0, s.t1, s.FE_VIA)
    am, pm = oc[:NB // 2].argmax(), NB // 2 + oc[NB // 2:].argmax()
    res.append((am * B, pm * B, oc[pm] / oc[am],
                (oc[:NB // 2] >= 0.7 * oc[am]).sum() * B, (oc[NB // 2:] >= 0.7 * oc[pm]).sum() * B))
r = np.array(res)
hm = lambda m: f'{int(m) // 60:02d}:{int(m) % 60:02d}'
linhas = [f'bootstrap por pessoa, {N_BOOT} reamostragens, IC95',
          'pico manhã: %s (%s-%s)' % (hm(np.median(r[:, 0])), hm(np.percentile(r[:, 0], 2.5)), hm(np.percentile(r[:, 0], 97.5))),
          'pico tarde: %s (%s-%s)' % (hm(np.median(r[:, 1])), hm(np.percentile(r[:, 1], 2.5)), hm(np.percentile(r[:, 1], 97.5))),
          'razão tarde/manhã: %.2f-%.2f' % tuple(np.percentile(r[:, 2], [2.5, 97.5])),
          'min >=70%% do pico, manhã: %d-%d' % tuple(np.percentile(r[:, 3], [2.5, 97.5])),
          'min >=70%% do pico, tarde: %d-%d' % tuple(np.percentile(r[:, 4], [2.5, 97.5]))]
(PROC / 'bootstrap_picos.txt').write_text('\n'.join(linhas) + '\n')
print('\n'.join(linhas))
