"""Horário de rush (seg-sex) das viagens associadas à Linha 11-Coral da CPTM (OD 2017).

A OD não registra a linha usada. Aproximação (mesma de 04_linhas.py): a viagem usa trem
(MODO = 2) E a origem ou o destino está a até RAIO m de uma estação da Linha 11
(coordenadas OSM, dados/brutos/osm_linha_11.json).
Variante "sem_integracao": descarta viagens cuja âncora é só estação de integração
(Luz, Brás, Tatuapé, Corinthians-Itaquera, Calmon Viana), onde a linha usada é mais ambígua.

Métrica: viagens em andamento por janela de 15 min (ponderado por FE_VIA), em % do pico.
Rush = janelas >= 70% do pico de cada metade do dia. Banda = IC95 por bootstrap de pessoas.

Saídas: dados/processados/perfil_linha11_15min.csv, dados/processados/bootstrap_picos_linha11.txt,
        figuras/rush_linha11_coral.png
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
B = 15          # minutos por janela
NB = 1440 // B
LIMIAR = 0.7    # fração do pico que define o rush

# estações em operação em 2017 (Luz-Estudantes; Palmeiras-Barra Funda entrou na linha depois)
L11 = ['Luz', 'Brás', 'Tatuapé', 'Corinthians-Itaquera', 'Dom Bosco', 'José Bonifácio', 'Guaianases',
       'Antonio Gianetti Neto', 'Ferraz de Vasconcelos', 'Poá', 'Calmon Viana', 'Suzano', 'Jundiapeba',
       'Braz Cubas', 'Mogi das Cruzes', 'Estudantes']
# integração com outra linha de trem/metrô: a viagem ancorada só aqui pode não usar a L11
INTEGRACAO = {'Luz', 'Brás', 'Tatuapé', 'Corinthians-Itaquera', 'Calmon Viana'}
COR = '#f04e23'

# --- coordenadas das estações (OSM, WGS84 -> SIRGAS 2000 / UTM 23S, mesmo sistema da OD) ---
osm = json.loads((RAIZ / 'dados/brutos/osm_linha_11.json').read_text())
utm = Transformer.from_crs('EPSG:4326', 'EPSG:31983', always_xy=True)
est = {}
for e in osm['elements']:
    if e['type'] == 'node' and e['tags'].get('name') in L11:
        est.setdefault(e['tags']['name'], utm.transform(e['lon'], e['lat']))
faltando = set(L11) - set(est)
assert not faltando, faltando

# --- viagens ---
df = pd.read_pickle(PROC / 'od2017_viagens.pkl').dropna(subset=['N_VIAG'])
df = df[df.DIA_SEM.between(2, 6)]                                   # seg-sex
df = df[df[['MODO1', 'MODO2', 'MODO3', 'MODO4']].isin([2]).any(axis=1)].reset_index(drop=True)  # 2 = trem

from dbfread import DBF  # coordenadas não estão no pkl: lê só as colunas necessárias
chave = {(r['ID_PESS'], r['N_VIAG']): (r['CO_O_X'], r['CO_O_Y'], r['CO_D_X'], r['CO_D_Y'])
         for r in DBF(RAIZ / 'dados/brutos/OD_2017_v1.dbf', load=False) if r['N_VIAG']}
xy = np.array([chave[(p, n)] for p, n in zip(df.ID_PESS, df.N_VIAG)], dtype=float)


def ancoras(so_nao_integracao):
    """bool por viagem: origem ou destino a <= RAIO de alguma estação da L11."""
    ok = np.zeros(len(df), bool)
    for nome in L11:
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
# M[i, k] = fração da janela k em que a viagem i está em andamento
M = np.zeros((len(df), NB))
for i, (a, b) in enumerate(zip(t0.astype(int), t1.astype(int))):
    np.add.at(M[i], np.arange(a, b) % 1440 // B, 1 / B)


def perfil(sel, w):
    return (w * sel) @ M    # viagens em andamento, média na janela


def rush(oc):
    """(pico manhã, pico tarde, janelas >= LIMIAR do pico em cada metade), em índices de janela."""
    am, pm = oc[:NB // 2].argmax(), NB // 2 + oc[NB // 2:].argmax()
    return am, pm, np.flatnonzero(oc[:NB // 2] >= LIMIAR * oc[am]), NB // 2 + np.flatnonzero(oc[NB // 2:] >= LIMIAR * oc[pm])


hm = lambda k: f'{int(k) * B // 60:02d}:{int(k) * B % 60:02d}'
w = df.FE_VIA.to_numpy()
pessoas, inv = np.unique(df.ID_PESS, return_inverse=True)
rng = np.random.default_rng(0)
boots = [np.bincount(rng.integers(0, len(pessoas), len(pessoas)), minlength=len(pessoas))[inv]
         for _ in range(N_BOOT)]   # peso extra de cada viagem = vezes que a pessoa foi sorteada

linhas_csv, res, txt = [], {}, []
for variante, excl in (('todas', False), ('sem_integracao', True)):
    sel = ancoras(excl)
    base = perfil(sel, w)
    bs = np.array([perfil(sel, w * k) for k in boots])
    pct = 100 * bs / bs.max(axis=1, keepdims=True)
    res[variante] = (100 * base / base.max(), *np.percentile(pct, [2.5, 97.5], axis=0))
    am, pm, jm, jt = rush(base)
    r = np.array([rush(o)[:2] for o in bs])
    txt += [f'{variante}: n={sel.sum()} viagens, {w[sel].sum() / 1e3:.0f} mil/dia (expandido)',
            f'  rush manhã (>= {LIMIAR:.0%} do pico): {hm(jm[0])}-{hm(jm[-1] + 1)}, pico {hm(am)} '
            f'(IC95 {hm(np.percentile(r[:, 0], 2.5))}-{hm(np.percentile(r[:, 0], 97.5))})',
            f'  rush tarde (>= {LIMIAR:.0%} do pico): {hm(jt[0])}-{hm(jt[-1] + 1)}, pico {hm(pm)} '
            f'(IC95 {hm(np.percentile(r[:, 1], 2.5))}-{hm(np.percentile(r[:, 1], 97.5))})',
            f'  razão tarde/manhã: {base[pm] / base[am]:.2f} '
            f'(IC95 {np.percentile(bs[np.arange(N_BOOT), r[:, 1]] / bs[np.arange(N_BOOT), r[:, 0]], 2.5):.2f}-'
            f'{np.percentile(bs[np.arange(N_BOOT), r[:, 1]] / bs[np.arange(N_BOOT), r[:, 0]], 97.5):.2f})']
    for k in range(NB):
        linhas_csv.append({'variante': variante, 'inicio': hm(k), 'n_amostra': int(sel.sum()),
                           'em_andamento_media': round(base[k]), 'pct_pico': res[variante][0][k],
                           'pct_ic95_inf': res[variante][1][k], 'pct_ic95_sup': res[variante][2][k]})
    if variante == 'todas':
        faixas = (jm, jt)
pd.DataFrame(linhas_csv).round(2).to_csv(PROC / 'perfil_linha11_15min.csv', index=False)
(PROC / 'bootstrap_picos_linha11.txt').write_text('\n'.join(txt) + '\n')
print('\n'.join(txt))

# --- figura ---
TINTA, TINTA2, GRADE, FUNDO = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
fig, ax = plt.subplots(figsize=(11, 4.8), facecolor=FUNDO)
ax.set_facecolor(FUNDO)
x = (np.arange(NB) + 0.5) * B / 60
for jj, rotulo in zip(faixas, ('rush manhã', 'rush tarde')):
    a, b = jj[0] * B / 60, (jj[-1] + 1) * B / 60
    ax.axvspan(a, b, color=COR, alpha=0.07, lw=0)
    ax.text((a + b) / 2, 104, f'{rotulo}\n{hm(jj[0])}–{hm(jj[-1] + 1)}', ha='center', va='bottom',
            fontsize=9, color=TINTA)
m, lo, hi = res['todas']
ax.fill_between(x, lo, hi, color=COR, alpha=0.2, lw=0)
ax.plot(x, m, color=COR, lw=2, label='Linha 11-Coral (todas as estações)')
ax.plot(x, res['sem_integracao'][0], color=COR, lw=1.2, ls='--',
        label='sem estações de integração\n(Luz, Brás, Tatuapé, C.-Itaquera, Calmon Viana)')
ax.axhline(100 * LIMIAR, color=TINTA2, lw=0.8, ls=':')
ax.set_xlim(0, 24)
ax.set_ylim(0, 122)
ax.set_yticks(range(0, 101, 20))
ax.set_xticks(range(0, 25, 2))
ax.set_xticklabels([f'{t:02d}h' for t in range(0, 25, 2)])
ax.set_ylabel('viagens em andamento (% do pico)', color=TINTA2)
ax.grid(axis='y', color=GRADE, lw=0.8)
for lado in ('top', 'right', 'left'):
    ax.spines[lado].set_visible(False)
ax.spines['bottom'].set_color(GRADE)
ax.tick_params(colors=TINTA2, length=0)
ax.legend(frameon=False, fontsize=8.5, loc='upper center', bbox_to_anchor=(0.48, 0.86), labelcolor=TINTA2)
ax.set_title('Horário de rush das viagens associadas à Linha 11-Coral (CPTM) — dias úteis, Pesquisa OD 2017',
             loc='left', fontsize=12, color=TINTA, pad=10)
fig.text(0.01, 0.01, f'Viagem com trem cuja origem ou destino fica a ≤{RAIO} m de estação da L11 (Luz–Estudantes, coord. OSM). '
         f'Janelas de {B} min;\nrush = ≥{LIMIAR:.0%} do pico (linha pontilhada). Banda = IC95 bootstrap por pessoa. '
         'Aproximação: a OD não registra a linha usada.', fontsize=7, color=TINTA2)
fig.tight_layout(rect=(0, 0.05, 1, 1))
saida = RAIZ / 'figuras/rush_linha11_coral.png'
fig.savefig(saida, dpi=150)
print('->', saida)
