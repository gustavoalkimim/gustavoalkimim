# 🐦 Flappy Bird AI — plano

Terceira IA do perfil, embaixo do Tetris. Mesma ideia (rede neural do zero em
C + algoritmo genético + treino semanal via Actions), mas com **o enxame
inteiro voando no GIF**. Esse é o diferencial visual que o Tetris não tem.

> Status: **só preparação.** Esta branch tem a estrutura de pastas, as
> interfaces em C (`engine/*.h`) e a seção reservada no README. Nada roda ainda.

## O problema a resolver: Flappy aprende rápido demais

No Flappy clássico, a neuroevolução resolve o jogo em ~10–20 gerações. É
o "hello world" da área. Se fizermos igual, a curva achata na primeira semana
e o projeto vira cópia de tutorial. Duas decisões resolvem isso:

1. **Dificuldade que sobe durante a partida (currículo dentro do voo):**
   - o vão entre os canos começa largo e vai fechando;
   - a velocidade horizontal aumenta aos poucos;
   - a partir do cano 50, os canos começam a **subir e descer** (senoide com fase sorteada);
   - a partir do cano 150, o espaçamento horizontal entre canos passa a variar.

   Um pássaro bom nas regras básicas morre nas fases avançadas, então a
   seleção continua tendo o que melhorar por meses.
2. **Teto de 500 canos por partida:** a fitness é limitada e o gráfico fica
   comparável ao longo do tempo.

## Física (passo fixo, 60 ticks/s)

| Constante | Valor inicial | Observação |
| --- | --- | --- |
| gravidade | 0.45 px/tick² | |
| impulso do pulo | −7.5 px/tick | substitui a velocidade, não soma |
| velocidade terminal | 10 px/tick | |
| velocidade dos canos | 3.0 → 5.0 px/tick | sobe 0.004 por cano |
| vão | 150 → 95 px | fecha 0.25 px por cano |
| distância entre canos | 220 px (varia ±40 a partir do cano 150) | |
| mundo | 288 × 512 px | proporção do jogo original |

Tudo em `double`, mas com semente fixa e passo fixo. O CI vai testar se o
replay é idêntico em duas execuções (igual ao Tetris).

## Rede neural

- **Entradas (6), normalizadas:**
  1. altura do pássaro
  2. velocidade vertical
  3. distância até o próximo cano
  4. topo do vão do próximo cano em relação ao pássaro
  5. base do vão do próximo cano em relação ao pássaro
  6. velocidade vertical do vão (por causa dos canos que se mexem)
- **Arquitetura:** 6 → 6 ocultos (tanh) → 1 saída. Pula se a saída > 0. São 49 pesos.
- Cada tick é uma decisão (o Tetris decide uma vez por peça). Por isso a rede é menor e o custo por decisão importa mais.

## Algoritmo genético

O mesmo esquema do Tetris, que já está calibrado:
- 100 pássaros por geração;
- elitismo de 5;
- seleção por torneio de 5;
- crossover uniforme;
- mutação gaussiana (taxa 0,10, sigma 0,25, 5% de saltos com sigma 1,0).

Avaliação:
- **todos os pássaros voam no mesmo mundo, ao mesmo tempo**, com a mesma semente. Isso é justo e é exatamente o que o GIF mostra;
- 3 mundos por geração, com sementes que mudam a cada geração;
- **fitness** = canos passados × 1000 + ticks vivo (desempate por quanto sobreviveu).

**Decisão em aberto:** copiar `ga.c`/`nn` do Tetris (cada projeto fica
independente) ou extrair um `common/` compartilhado (menos código duplicado,
mas os dois Makefiles e CIs passam a depender dele). Sugestão: **copiar** na
v1 e extrair depois, se um terceiro projeto precisar.

**Ritmo:** começar com 2 gerações por semana, como o Tetris. Calibrar
rodando ~80 gerações localmente antes de publicar, com a meta de ~3 meses de
curva subindo.

## O que aparece no perfil

1. **`flappy/swarm.gif`:** os 100 pássaros da geração atual voando juntos,
   semitransparentes, e o campeão destacado em roxo, com contador
   "alive 37/100", número da geração e canos passados. Quando um pássaro
   morre, ele cai e some. Nas primeiras semanas quase todos morrem no
   primeiro cano; meses depois, o enxame atravessa as fases.
2. **`flappy/evolution.svg`:** gráfico de canos passados por geração
   (melhor e média), com faixas marcando onde começam as fases
   (canos móveis, espaçamento variável).
3. Tabela no README: geração, semanas treinando, recorde, fase mais avançada alcançada.

Tamanho do GIF: uns 600 quadros com 100 sprites cada. Precisa caber em
~1,5 MB, com paleta fixa e um pássaro de 2 a 3 cores.

## Interface da engine (CLI usada pelo Action)

```
flappy train  <população.txt> <gerações> [tamanho]   # uma linha JSON por geração
flappy replay <população.txt> <semente> <máx_ticks>  # todos os pássaros, quadro a quadro, em JSON
```

O `replay` exporta **o enxame inteiro**: por tick, a posição y de cada
pássaro vivo e a posição dos canos. O Python só desenha.

## Arquivos

| Arquivo | Conteúdo | Status |
| --- | --- | --- |
| `engine/game.h` | mundo, pássaro, canos, física, currículo | interface pronta |
| `engine/ai.h` | entradas e rede neural | interface pronta |
| `engine/ga.h` | população e evolução | interface pronta |
| `engine/game.c`, `ai.c`, `ga.c`, `main.c` | implementação | a fazer |
| `engine/Makefile` | build | pronto (falta o código) |
| `render.py` | GIF do enxame, SVG da evolução, seção do README | a fazer |
| `data/` | `population.txt` + `history.json` (versionados) | a fazer |
| `.github/workflows/flappy.yml` | treino semanal (segunda, 10:00 UTC, depois do Tetris) | a fazer |
| `.github/workflows/flappy-engine-ci.yml` | `-Werror`, determinismo, treino roda | a fazer |

## Checklist de implementação

- [ ] `game.c`: física, geração de canos com semente, currículo e colisão
- [ ] `ai.c`: entradas normalizadas e forward da rede
- [ ] `ga.c`: avaliação em enxame (todos no mesmo mundo) e evolução
- [ ] `main.c`: `train` e `replay`
- [ ] Calibrar: 80 gerações locais, ajustar o currículo até a curva durar meses
- [ ] `render.py`: GIF do enxame (com a meta de tamanho), SVG e README
- [ ] Workflows de treino e de CI
- [ ] Gerar a geração 0 e conferir o visual
- [ ] Descomentar a seção no README principal. Os marcadores estão sem `<!-- -->`,
      porque comentário dentro de comentário quebra o HTML. Ao descomentar, eles viram
      `<!--START_SECTION:flappy-->` e `<!--END_SECTION:flappy-->`.
