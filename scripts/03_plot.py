"""Plota o ciclo diurno (viagens com metrô em andamento) e marca os rushes (>=70% do pico).

Entrada: dados/processados/ciclo_metro_15min.csv
Saída:   figuras/ciclo_metro_od2017.png
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
LIMIAR = 70  # % do pico do dia que define "rush"

TINTA, TINTA2, GRADE = '#0b0b0b', '#52514e', '#e4e3df'
SERIE, FAIXA = '#2a78d6', '#cde2fb'

df = pd.read_csv(RAIZ / 'dados/processados/ciclo_metro_15min.csv')
h = np.arange(len(df)) * 15 / 60 + 7.5 / 60      # centro da janela, em horas
y = df.em_andamento / 1e3

fig, ax = plt.subplots(figsize=(11, 4.8), facecolor='#fcfcfb')
ax.set_facecolor('#fcfcfb')

# faixas de rush: trechos contíguos acima do limiar
acima = (df.pct_pico >= LIMIAR).to_numpy()
ini = None
for i, a in enumerate(np.append(acima, False)):
    if a and ini is None:
        ini = i
    elif not a and ini is not None:
        x0, x1 = ini * 0.25, i * 0.25
        ax.axvspan(x0, x1, color=FAIXA, lw=0, zorder=0)
        ax.text((x0 + x1) / 2, y.max() * 1.07, f'{df.inicio[ini]}–{df.inicio[i] if i < len(df) else "24:00"}',
                ha='center', va='bottom', fontsize=9, color=TINTA2)
        ini = None

ax.plot(h, y, color=SERIE, lw=2, zorder=3)
ax.axhline(y.max() * LIMIAR / 100, color=TINTA2, lw=0.8, ls=(0, (3, 3)), zorder=2)
ax.text(0.2, y.max() * LIMIAR / 100, f'{LIMIAR}% do pico', fontsize=8, color=TINTA2, va='bottom')

ax.set_xlim(0, 24)
ax.set_ylim(0, y.max() * 1.18)
ax.set_xticks(range(0, 25, 2))
ax.set_xticklabels([f'{t:02d}h' for t in range(0, 25, 2)])
ax.set_ylabel('viagens em andamento (mil)', color=TINTA2)
ax.grid(axis='y', color=GRADE, lw=0.8)
for lado in ('top', 'right', 'left'):
    ax.spines[lado].set_visible(False)
ax.spines['bottom'].set_color(GRADE)
ax.tick_params(colors=TINTA2, length=0)
ax.set_title('Viagens que usam metrô em andamento ao longo do dia útil — Pesquisa OD 2017',
             loc='left', fontsize=12, color=TINTA)
fig.text(0.01, 0.01, 'Fonte: microdados Pesquisa Origem-Destino 2017, Metrô SP. Janelas de 15 min, ponderado por FE_VIA. '
         'Horário da viagem inteira (inclui a pé/ônibus); faixas = rush (≥70% do pico).',
         fontsize=7.5, color=TINTA2)
fig.tight_layout(rect=(0, 0.03, 1, 1))
saida = RAIZ / 'figuras/ciclo_metro_od2017.png'
fig.savefig(saida, dpi=150)
print('->', saida)
