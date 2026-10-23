"""Perfil horário (seg-sex) das viagens associadas às linhas 2-Verde e 4-Amarela (OD 2017).

A OD não registra a linha usada. Aproximação: a viagem usa metrô/monotrilho E
a origem ou o destino está a até RAIO m de uma estação da linha (coordenadas OSM,
dados/brutos/osm_linhas_2_4.json). Uma viagem pode cair nas duas linhas.
Variante "exclusiva": descarta viagens cuja âncora é só estação de integração,
onde a linha usada é mais ambígua.

Métrica: viagens em andamento, média na hora (ponderado por FE_VIA), e % do total
do dia de cada linha. Banda = IC95 por bootstrap de pessoas.

Saídas: dados/processados/perfil_horario_linhas.csv, figuras/perfil_horario_l2_l4.png
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyproj import Transformer

RAIZ = Path(__file__).resolve().parent.parent
PROC = RAIZ / 'dados/processados'
RAIO = 800      # m, distância a pé típica até a estação
N_BOOT = 200

# estações em operação em 2017 (Higienópolis, Oscar Freire, S. Paulo-Morumbi e Vila Sônia abriram depois)
L2 = ['Vila Madalena', 'Sumaré', 'Clínicas', 'Consolação', 'Trianon-Masp', 'Brigadeiro', 'Paraíso',
      'Ana Rosa', 'Chácara Klabin', 'Santos - Imigrantes', 'Alto do Ipiranga', 'Sacomã',
      'Tamanduateí', 'Vila Prudente']
L4 = ['Luz', 'República', 'Paulista', 'Fradique Coutinho', 'Faria Lima', 'Pinheiros', 'Butantã']
# integração com outra linha de metrô/trem: a viagem ancorada só aqui pode não usar L2/L4
INTEGRACAO = {'Consolação', 'Paraíso', 'Ana Rosa', 'Tamanduateí', 'Vila Prudente',
              'Luz', 'República', 'Paulista', 'Pinheiros'}
LINHAS = {'Linha 2-Verde': (L2, '#008300'), 'Linha 4-Amarela': (L4, '#c98500')}

# --- coordenadas das estações (OSM, WGS84 -> SIRGAS 2000 / UTM 23S, mesmo sistema da OD) ---
osm = json.loads((RAIZ / 'dados/brutos/osm_linhas_2_4.json').read_text())
utm = Transformer.from_crs('EPSG:4326', 'EPSG:31983', always_xy=True)
est = {}
for e in osm['elements']:
    if e['type'] != 'node':
        continue
    nome = e['tags'].get('name', '')
    for alvo in L2 + L4:
        if nome.startswith(alvo) or (alvo == 'Sumaré' and 'Sumaré' in nome):
            est.setdefault(alvo, utm.transform(e['lon'], e['lat']))
faltando = set(L2 + L4) - set(est)
assert not faltando, faltando

# --- viagens ---
df = pd.read_pickle(PROC / 'od2017_viagens.pkl').dropna(subset=['N_VIAG'])
df = df[df.DIA_SEM.between(2, 6)]                                   # seg-sex
df = df[df[['MODO1', 'MODO2', 'MODO3', 'MODO4']].isin([1, 3]).any(axis=1)].reset_index(drop=True)

from dbfread import DBF  # coordenadas não estão no pkl: lê só as colunas necessárias
chave = {(r['ID_PESS'], r['N_VIAG']): (r['CO_O_X'], r['CO_O_Y'], r['CO_D_X'], r['CO_D_Y'])
         for r in DBF(RAIZ / 'dados/brutos/OD_2017_v1.dbf', load=False) if r['N_VIAG']}
xy = np.array([chave[(p, n)] for p, n in zip(df.ID_PESS, df.N_VIAG)], dtype=float)


def ancoras(lista, so_nao_integracao):
    """bool por viagem: origem ou destino a <= RAIO de alguma estação da lista."""
    ok = np.zeros(len(df), bool)
    for nome in lista:
        if so_nao_integracao and nome in INTEGRACAO:
            continue
        ex, ey = est[nome]
        for ix, iy in ((0, 1), (2, 3)):
            ok |= np.hypot(xy[:, ix] - ex, xy[:, iy] - ey) <= RAIO
    return ok


t0 = (df.H_SAIDA * 60 + df.MIN_SAIDA).to_numpy()
t1 = (df.H_CHEG * 60 + df.MIN_CHEG).to_numpy()
t1 = np.where(t1 < t0, t1 + 1440, t1)
t1 = np.maximum(t1, t0 + 1)
# M[i, h] = fração da hora h em que a viagem i está em andamento
M = np.zeros((len(df), 24))
for i, (a, b) in enumerate(zip(t0.astype(int), t1.astype(int))):
    np.add.at(M[i], np.arange(a, b) % 1440 // 60, 1 / 60)


def perfil(sel, w):
    return (w * sel) @ M    # viagens em andamento, média na hora


w = df.FE_VIA.to_numpy()
pessoas, inv = np.unique(df.ID_PESS, return_inverse=True)
rng = np.random.default_rng(0)
boots = [np.bincount(rng.integers(0, len(pessoas), len(pessoas)), minlength=len(pessoas))[inv]
         for _ in range(N_BOOT)]   # peso extra de cada viagem = vezes que a pessoa foi sorteada

linhas_csv, res = [], {}
for nome, (lista, _) in LINHAS.items():
    for variante, excl in (('todas', False), ('sem_integracao', True)):
        sel = ancoras(lista, excl)
        base = perfil(sel, w)
        bs = np.array([perfil(sel, w * k) for k in boots])
        pct = 100 * bs / bs.sum(axis=1, keepdims=True)
        res[nome, variante] = (100 * base / base.sum(), *np.percentile(pct, [2.5, 97.5], axis=0))
        print(f'{nome:16s} {variante:15s} n={sel.sum():5d}  viagens/dia={w[sel].sum() / 1e3:7.0f} mil  '
              f'pico manhã {base[:12].argmax():02d}h  pico tarde {12 + base[12:].argmax():02d}h')
        for hh in range(24):
            linhas_csv.append({'linha': nome, 'variante': variante, 'hora': hh, 'n_amostra': int(sel.sum()),
                               'em_andamento_media': round(base[hh]), 'pct_dia': res[nome, variante][0][hh],
                               'pct_ic95_inf': res[nome, variante][1][hh], 'pct_ic95_sup': res[nome, variante][2][hh]})
pd.DataFrame(linhas_csv).round(2).to_csv(PROC / 'perfil_horario_linhas.csv', index=False)

# --- figura: as duas linhas nos mesmos eixos (variante "todas"; banda = IC95) ---
TINTA, TINTA2, GRADE, FUNDO = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
fig, ax = plt.subplots(figsize=(11, 4.8), facecolor=FUNDO)
ax.set_facecolor(FUNDO)
x = np.arange(24) + 0.5
for nome, (_, cor) in LINHAS.items():
    m, lo, hi = res[nome, 'todas']
    ax.fill_between(x, lo, hi, color=cor, alpha=0.15, lw=0)
    ax.plot(x, m, color=cor, lw=2, marker='o', ms=4, label=nome)
ax.set_xlim(0, 24)
ax.set_ylim(0, None)
ax.set_xticks(range(0, 25, 2))
ax.set_xticklabels([f'{t:02d}h' for t in range(0, 25, 2)])
ax.set_ylabel('% das viagens-hora do dia', color=TINTA2)
ax.grid(axis='y', color=GRADE, lw=0.8)
for lado in ('top', 'right', 'left'):
    ax.spines[lado].set_visible(False)
ax.spines['bottom'].set_color(GRADE)
ax.tick_params(colors=TINTA2, length=0)
ax.legend(frameon=False, fontsize=9, loc='upper left', labelcolor=TINTA2)
ax.set_title('Perfil horário das viagens associadas às linhas 2 e 4 — dias úteis, Pesquisa OD 2017',
             loc='left', fontsize=12, color=TINTA)
fig.text(0.01, 0.01, f'Viagem com metrô cuja origem ou destino fica a ≤{RAIO} m de estação da linha (estações de 2017, coord. OSM). '
         'Banda = IC95 bootstrap por pessoa. Aproximação: a OD não registra a linha usada.',
         fontsize=7.5, color=TINTA2)
fig.tight_layout(rect=(0, 0.03, 1, 1))
saida = RAIZ / 'figuras/perfil_horario_l2_l4.png'
fig.savefig(saida, dpi=150)
print('->', saida)
