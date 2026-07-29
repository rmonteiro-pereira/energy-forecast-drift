# P4 — Previsão de demanda de energia + ML
Ops + drift LIVE (guia executável)
**Objetiv
o:** um forecaster de demanda de energia **at
ualizando sozinho** (dado vivo via API), com 
**MLOps** (MLflow, serving) e **monitoramento
 de drift real** (PSI/KS + performance) — t
udo **open-source e ~R$0**, com um demo **liv
e** hospedado de graça. Prova o lado **Cient
ista de Dados** + MLOps/serving.

> Frase-alv
o de entrevista: *"Tenho um forecaster de dem
anda de energia que se atualiza sozinho por u
m cron gratuito, com backtesting walk-forward
, MLflow, serving, e um monitor de drift (PSI
/KS + degradação de MAE) que dispara retrei
no — dá pra ver o drift acumulando ao vivo
 no dashboard."*

---

## Dataset (VIVO — c
ondição pro drift ser real)
- **EIA Open Da
ta API v2** — demanda elétrica **horária*
* por região (balancing authority), **gráti
s** (API key), **atualiza ~2×/dia**. Sazonal
idade forte + puxada por clima + regime = **d
rift genuíno**. (eia.gov/opendata)
- **+ cli
ma como feature/fonte de drift:** **Open-Mete
o API** (grátis, sem key) — temperatura po
r região.
- Alternativa Europa: **ENTSO-E Tr
ansparency** (carga horária).
- **Nunca** Ka
ggle congelado aqui — não haveria drift.


## Stack (100% aberta, ~R$0)
| Camada | Escol
ha | Nota |
|---|---|---|
| Ingestão | `requ
ests`/`httpx` → EIA + Open-Meteo | grátis 
|
| Store | Parquet/DuckDB (append incrementa
l) | local/repo |
| Features | Pandas/Polars:
 calendário, lags, rolling, temperatura | �
� |
| Baseline | seasonal naive / última sem
ana | obrigatório (bater depois) |
| Modelo 
| **LightGBM** (global, lags+calendário) ou 
**statsforecast** (AutoETS/ARIMA) | aberto |

| Backtest | **walk-forward** (janela desliza
nte) | rigor que junior erra |
| Tracking | *
*MLflow** (sqlite backend + registry) | abert
o |
| Drift | **Evidently** (relatórios) + P
SI/KS próprios | aberto, o coração |
| Ser
ving | **FastAPI** `/forecast` (carrega model
o do registry) | aberto |
| Dashboard | **Rea
ct** (Next.js/Vite + Recharts/ECharts, lê `m
etrics/` JSON) | Vercel/CF Pages grátis, nã
o dorme |
| Scheduler | **GitHub Actions cron
** | grátis em repo público |

## Estrutura
 do repo
```
energy-forecast-drift/
  README.
md                 # diagrama, decisões, MAE
/drift antes-depois
  ingest/                
   # EIA + Open-Meteo → append parquet/duck
db
  features/                 # calendário,
 lags, rolling, join clima
  models/         
          # baseline + LightGBM/statsforecast
 + walk-forward
  drift/                    #
 Evidently + PSI/KS + thresholds
  monitor/  
                # métricas rolling (MAE/MAPE
) quando actual chega
  serving/             
     # FastAPI /forecast
  dashboard/        
        # React (Next.js/Vite + Recharts/ECha
rts, lê metrics/)
  metrics/                
  # JSON/PNG commitados pelo cron (o "live")

  .github/workflows/
    daily.yml           
    # cron: pull → score → drift → comm
it metrics
    ci.yml                  # test
es + gate de backtest
  docs/writeup.md
```


---

## Milestones (ordem executável)

**M0 
— Scaffolding + ingestão.** Repo + client 
da EIA (uma região, ex.: PJM/CAL) + Open-Met
eo. Append incremental em parquet/DuckDB. Obj
etivo: rodar `ingest` e ter histórico + sabe
r puxar o delta.

**M1 — Baseline.** Season
al naive (mesma hora, semana passada) + backt
est. **É o número a bater** — sem baselin
e, não há história.

**M2 — Modelo + wal
k-forward.** LightGBM global (features: hora/
dow/mês/feriado, lags 24h/168h, rolling, tem
peratura). **Backtesting walk-forward** (trei
na até T, prevê T+h, desliza). Reporta MAE/
MAPE por horizonte vs baseline. *Rigor: sem l
eakage temporal.*

**M3 — MLflow.** Trackin
g de experimentos + registry (versiona o mode
lo campeão). Serving carrega do registry.

*
*M4 — Drift (o diferenciador).** Com **Evid
ently** + PSI/KS próprios, medir 4 tipos:
- 
*Feature drift:* distribuição das features 
recentes vs janela de treino (PSI/KS).
- *Tar
get drift:* distribuição da demanda desloca
 (sazonal/regime).
- *Prediction drift:* dist
ribuição das previsões.
- *Performance dri
ft:* MAE/MAPE rolling degradando (usa os **ac
tuals que chegam** no pull diário).
Definir 
**thresholds** (ex.: PSI>0.2 = alerta) e **tr
igger de retreino**.

**M5 — Cron LIVE (a s
acada R$0).** `daily.yml` (GitHub Actions): p
uxa dado fresco → gera features → score �
�� quando actual chega, calcula MAE rolling +
 drift → **commita `metrics/*.json` + `*.pn
g`** (forecast, drift no tempo, MAE trend) no
 repo. Sem servidor ligado; a frescura vem do
 cron.

**M6 — Dashboard + serving.** **Das
hboard React** (Next.js/Vite + Recharts/EChar
ts) lê `metrics/*.json` (do repo ou R2, clie
nt-side) → forecast vs actual, **drift acum
ulando no tempo**, MAE trend, status de alert
a. Hospeda no **Vercel / Cloudflare Pages** (
grátis, estático, **não dorme**, deploy no
 push). FastAPI `/forecast` opcional em HF Sp
aces/Render.

**M7 — Writeup.** README com 
diagrama, decisão de modelo, MAE vs baseline
, e **um episódio de drift real** capturado 
(ex.: onda de calor → demanda desloca → a
lerta disparou → retreino). Esse episódio 
é o **ouro da entrevista**.

---

## A profu
ndidade que separa junior de sênior
- **Base
line-first** e **walk-forward** (nunca split 
aleatório em série temporal).
- **Sem leaka
ge:** feature no tempo T só usa dado ≤ T.

- **4 tipos de drift** (feature/target/predic
tion/performance), não só "data drift" gen�
�rico.
- **Trigger de retreino** ligado a thr
eshold — mostra que você opera, não só t
reina.
- **Unit economics:** custo (R$0), lat
ência do serving, tamanho do modelo.

## Hos
ting (recap, sem homelab)
Cron (**GitHub Acti
ons**, grátis, não é o homelab) mantém `m
etrics/*.json` fresco (commit no repo ou push
 pro **R2**) → **dashboard React** (Vercel/
CF Pages, estático, **não dorme**) lê os a
rtefatos. **Live de verdade, R$0, na nuvem.**
 24/7 real opcional: **Oracle Cloud Always Fr
ee**.

## Dupla função (opcional)
Casa com 
uma **frente do mestrado** sobre monitorament
o/drift de modelos em produção, ou fica com
o o projeto de MLOps "de mercado" (padrão co
nsagrado — ver `referencias-treino-e-portfo
lio.md`).

## Kickoff (essa semana)
1. Pega A
PI key da EIA (grátis) + escolhe uma região
 com sazonalidade forte.
2. `ingest` puxa o h
istórico + testa o delta diário.
3. Faz o M
1 (baseline + backtest) e **anota o MAE** —
 é seu ponto de partida.
4. Sobe o `daily.ym
l` cedo (mesmo simples) pra o "live" começar
 a acumular histórico desde já.

> Regra de
 ouro: **o cron e o baseline entram cedo.** O
 valor do projeto é o drift acumulando ao lo
ngo das semanas — quanto antes ligar, mais 
história você tem quando for entrevistar.


