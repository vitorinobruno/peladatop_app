# CLAUDE.md — PeladaTop

Contexto geral do projeto para uso em sessões de desenvolvimento com Claude Code.

---

## Visão Geral

**PeladaTop** é uma aplicação de gerenciamento de peladas (futebol recreativo).
Permite organizar atletas, confirmar presenças, sortear times, conduzir jogos em tempo real e acompanhar estatísticas históricas.

**Arquitetura:** Backend FastAPI (Python) + App mobile Flutter.
**Deploy:** Backend no Render.com (PostgreSQL). Mobile distribuído como APK/App Store.

---

## Estrutura do Projeto

```
peladatop_app/
├── backend/
│   ├── main.py          # Todos os endpoints FastAPI
│   ├── models.py        # Modelos SQLModel (ORM)
│   ├── database.py      # Engine SQLite (dev) / PostgreSQL (prod)
│   ├── requirements.txt
│   └── runtime.txt      # Python 3.14.0
│
└── mobile/peladatop_mobile/
    └── lib/
        ├── main.dart                   # Entry point, rotas
        ├── config/api_config.dart      # Base URL da API
        ├── models/                     # Atleta, Pelada, TimeModel
        ├── providers/pelada_provider.dart  # State (pelada ativa)
        ├── services/                   # AtletaService, PeladaService
        ├── screens/                    # Todas as telas
        └── theme/app_theme.dart        # Material 3, azul/verde
```

---

## Backend

### Banco de Dados

- **Dev:** SQLite (`database.db` local)
- **Prod:** PostgreSQL via `DATABASE_URL` (Render.com)
- Tabelas criadas automaticamente no startup (`SQLModel.metadata.create_all`)

### Modelos Principais

| Modelo | Campos relevantes |
|--------|------------------|
| `Atleta` | `id, nome, nivel (1–3), posicao, mensalista, titulos` |
| `Pelada` | `id, data, local, status (planejada/em_andamento/finalizada), campeao, deletada` |
| `Presenca` | `pelada_id, atleta_id, confirmado` |
| `Time` | `id, pelada_id, nome, cor` |
| `TimeAtleta` | `time_id, atleta_id` (N:N) |
| `Jogo` | `id, pelada_id, time_a_id, time_b_id, gols_a, gols_b, tempo_minutos, pausavel, status` |
| `Partida` | `id, jogo_id, tempo_minutos, placar_a, placar_b, status` |
| `EventoPartida` | `partida_id, time_id, atleta_gol_id, atleta_assistencia_id, instante_segundos` |

### Endpoints (resumo)

```
# Atletas
POST   /atletas
GET    /atletas
PUT    /atletas/{id}
POST   /atletas/{id}/importar-stats

# Peladas
POST   /peladas
GET    /peladas              ?data_inicio=&data_fim=  (ordenado desc, exclui deletadas)
DELETE /peladas/{id}         (soft delete — marca deletada=True, não apaga o registro)

# Presenças
POST   /peladas/{id}/presencas
GET    /peladas/{id}/presencas
GET    /peladas/{id}/presencas-completo
GET    /peladas/{id}/presenca-link       (página HTML WhatsApp)

# Times
POST   /peladas/{id}/times   (3 cenários: sem jogos / jogos sem iniciar / jogo em andamento)
GET    /peladas/{id}/times

# Jogos
POST   /peladas/{id}/jogos   ?tempo_minutos=&pausavel=  (bool, default false)
GET    /peladas/{id}/jogos

# Partidas (tempo real)
POST   /jogos/{id}/partida
GET    /partidas/{id}        → inclui campos "goleiros" (confirmados na pelada) e "eventos" (ordenados por instante)
POST   /partidas/{id}/gol
PUT    /partidas/{id}/gol/{evento_id}   → edita marcador/assistente sem alterar instante_segundos
POST   /partidas/{id}/finalizar

# Classificação e finalização
GET    /peladas/{id}/classificacao
POST   /peladas/{id}/finalizar

# Estatísticas
GET    /estatisticas/gols          ?pelada_id=
GET    /estatisticas/assistencias  ?pelada_id=
GET    /estatisticas/titulos
GET    /estatisticas/pontos-ano    ?ano=  (filtro opcional por ano)

# Resenha IA
POST   /peladas/{id}/resenha       → gera resenha narrativa via Groq (retorna texto plain)
                                     body: { "detalhes_extras": "..." } (opcional)
```

### Lógica de Negócio Importante

**Geração de jogos:**
- 2 times → 1 jogo (A vs B)
- 3 times → todos contra todos (cada par joga 2x)

**Salvar times (`POST /times`) — 3 cenários:**
1. Sem jogos gerados → apaga times existentes e recria do zero
2. Jogos gerados, nenhum iniciado → apaga jogos + times e recria
3. Algum jogo iniciado/finalizado → apenas atualiza atletas dos times

**Classificação:** Vitória=3pts, Empate=1pt. Desempate: saldo de gols > gols pró.

**Finalizar pelada:** Define campeão (time com mais pontos), incrementa `titulos` dos atletas do time vencedor. Em caso de empate perfeito (pontos + saldo + gols pró iguais), `campeao` fica `None` e nenhum título é incrementado.

**Goleiros — regra especial:** Goleiros não são fixos nos times (há revezamento). Por isso:
- `GET /partidas/{id}` retorna campo `goleiros`: lista de todos os goleiros confirmados na pelada
- No dialog de gol (`PartidaScreen`), goleiros aparecem na lista de qualquer time, sem precisar estar formalmente atribuídos
- Em `ResultadosScreen`, goleadores/assistentes filtram por atletas dos times **+** goleiros confirmados, para que seus gols e assistências apareçam normalmente
- `GET /peladas/{id}/presencas` inclui `nivel` no retorno (necessário para o sorteio por força)

**Presenças — upsert:** `POST /peladas/{id}/presencas` verifica se já existe registro antes de inserir; se sim, atualiza `confirmado=True` (evita duplicatas).

**Edição de gols pós-partida:** Partidas finalizadas podem ter gols adicionados ou editados via `PartidaScreen` (modo somente leitura). Um gol adicionado após finalização recebe `instante_segundos = tempo_total` (último segundo), aceitável para estatísticas. A edição via `PUT /partidas/{id}/gol/{evento_id}` preserva o instante original.

**Resenha gerada por IA:** `POST /peladas/{id}/resenha` usa Groq (modelo `llama-3.3-70b-versatile`) para gerar uma narrativa bem humorada da pelada com todos os jogos, gols e assistentes. Requer variável de ambiente `GROQ_API_KEY` no servidor. Aceita campo opcional `detalhes_extras` para enriquecer o texto com contexto fornecido pelos participantes.

**Sorteio de times — goleiros excluídos:** Goleiros não entram no sorteio automático (`_sortearTimes`). Ficam disponíveis apenas para adição manual via seleção de atletas no card do time.

**Pause do cronômetro:** Campo `pausavel` no modelo `Jogo` (bool, default `false`). Configurado em `JogosScreen` via `SwitchListTile` antes de gerar os jogos — padrão `true` para peladas de 2 times, `false` para 3 times. O pause é **frontend-only**: cancela o `Timer.periodic` local, preservando `segundosRestantes`. O backend não é afetado. Registro de gols e finalização da partida continuam totalmente manuais independente do estado do cronômetro. Se o usuário sair da tela e voltar, `_calcularTempo()` recalcula o tempo a partir do wall clock (perde o estado de pause).

---

## Mobile (Flutter)

### Configuração

- **Base URL:** `https://peladatop-app.onrender.com` (`lib/config/api_config.dart`) — `static String baseUrl` (mutável para suporte a flavors)
- **State management:** Provider (`PeladaProvider` — guarda a pelada ativa globalmente)
- **HTTP:** `package:http` com decode UTF-8 (`utf8.decode(res.bodyBytes)`)

### Product Flavors (Android)

| Flavor | App Name | Application ID | Backend |
|--------|----------|---------------|---------|
| `sabado` | PeladaTop | `com.example.peladatop_mobile` | `https://peladatop-app.onrender.com` |
| `quinta` | PeladaTop Quinta | `com.example.peladatop_quinta` | `https://peladatop-app-quinta.onrender.com` |

- Entry point do flavor quinta: `lib/main_quinta.dart` (sobrescreve `ApiConfig.baseUrl` antes do `runApp`)
- Configuração de URL da quinta: `lib/config/api_config_quinta.dart`
- Build: `flutter build apk --flavor quinta -t lib/main_quinta.dart --release`
- `ApiConfig.baseUrl` é `static String` (não `const`) para permitir override em runtime; services usam getter `static String get baseUrl => ApiConfig.baseUrl`

### Navegação

```
PeladasScreen (/)           ← tela raiz com BottomNavBar
  BottomNav: Peladas | Atletas | Times | Jogos
  AppBar actions: Resultados | Estatísticas

Rotas nomeadas:
  /criar-pelada   CriarPeladaScreen
  /presenca       PresencaScreen
  /partida        PartidaScreen
  /resultados     ResultadosScreen
  /estatisticas   EstatisticasScreen
```

### Fluxo Completo de uma Pelada

```
1. Criar pelada (data + local)
2. Confirmar presenças dos atletas (PresencaScreen)
3. Distribuir em times — manual ou sorteio automático (TimesScreen)
4. Gerar jogos com tempo definido (JogosScreen)
5. Abrir cada jogo → registrar gols em tempo real (PartidaScreen)
6. Finalizar pelada → definir campeão (ResultadosScreen)
```

### Posições de Atleta

`goleiro`, `zagueiro`, `ala`, `volante`, `atacante`

### Cores de Time

`Branco`, `Azul`, `Laranja`, `Verde`

### Comportamento de Telas Importantes

**PresencaScreen:**
- Atletas agrupados em: Goleiros | Mensalistas | Convidados
- Atletas já confirmados exibem ListTile com checkmark verde + botão de cancelar (ícone vermelho)
- Goleiros são separados dos convidados — não aparecem nas duas listas
- Compartilha link de presença via WhatsApp

**JogosScreen:**
- Partidas não iniciadas: placar exibe "—"
- Partidas finalizadas: botão discreto "Ver partida" (OutlinedButton cinza) em vez de texto estático
- Card de configuração (antes de gerar jogos) inclui slider de tempo e `SwitchListTile` para habilitar botão de pause

**PartidaScreen:**
- Ícone de histórico na AppBar abre bottom sheet com lista de gols registrados
- Cada gol no histórico tem botão de edição (altera marcador/assistente sem perder o instante)
- Quando partida está finalizada: tela em modo leitura, sem botão "Registrar Gol" nem "Encerrar"
- Gols adicionados pós-finalização ficam disponíveis via "Adicionar gol" no bottom sheet de histórico
- Botão de pause discreto (OutlinedButton) abaixo do cronômetro — visível apenas quando `pausavel=true` e partida não finalizada; alterna entre pausar/retomar o timer local

**ResultadosScreen:**
- Goleadores/assistentes incluem goleiros confirmados (não apenas atletas dos times)
- Lista completa é exibida intencionalmente (sem limite) para exportação via WhatsApp
- Botão "Gerar Resenha" abre dialog com opção de adicionar detalhes extras, gera narrativa via IA e exibe com botão de compartilhar no WhatsApp
- Botão "Gerar Card ⚽" captura widget estilizado 1080×1080 (fundo escuro, placares, artilheiros, campeão com cor do time) e compartilha como PNG via `share_plus`

### Algoritmo de Sorteio (`_sortearTimes`)

Composição ideal por time: `{ zagueiro:3, volante:1, ala:3, atacante:2 }`

**Goleiros são excluídos do sorteio automático** — adição apenas manual.

4 passos (apenas atletas não-goleiros):
1. Snake draft por posição (dentro da composição)
2. Posições fora da composição → time com menos atletas
3. Balanceamento de tamanho (diferença ≤ 1 atleta)
4. Balanceamento de força — troca pares de mesma posição até diferença de nível ≤ 1

---

## Cache de Leitura (Mobile)

Cache em memória implementado nos services para evitar requests repetidos durante navegação entre telas. Escritas (POST/PUT) nunca passam por cache — vão sempre direto ao servidor.

| Service | Método | TTL | Invalidado por |
|---|---|---|---|
| `AtletaService` | `getAtletas` | 5 min | `criarAtleta`, `editarAtleta` |
| `PeladaService` | `getPresencas` | 2 min | `confirmarPresencas`, `cancelarPresenca` |
| `PeladaService` | `getTimes` | 5 min | `salvarTimes` |
| `PeladaService` | `getJogos` | 1 min | `criarJogos`, `salvarTimes` |

**Nota:** `obterPartida` não é cacheado — é consultado durante partidas ativas onde os dados mudam com frequência.

**Optimistic updates foram descartados** para registro/edição de gols: o Render.com gratuito tem latência imprevisível (cold starts de 10–20s), o que tornaria rollbacks tardios piores do que a espera original.

---

## Dependências

### Backend
```
fastapi, uvicorn, sqlmodel, sqlalchemy, pydantic
psycopg2-binary (PostgreSQL prod)
groq (resenha IA)
pandas, numpy (scripts de importação)
```

### Mobile
```
http: ^1.2.2
provider: ^6.1.5+1
url_launcher: ^6.2.5   # Exportar para WhatsApp
screenshot: ^2.3.0     # Captura de widget para card PNG (Flutter 3.19.6 requer ^2.x, não ^3.x)
share_plus: ^9.0.0     # Compartilhar arquivos via WhatsApp/outros
path_provider: ^2.1.0  # Diretório temporário para salvar PNG
```

---

## Pontos de Atenção

- CORS configurado com `allow_origins=["*"]` — aceitável para o contexto atual
- Não há autenticação/autorização nos endpoints
- Testes automáticos inexistentes (apenas smoke test genérico do Flutter)
- Nível dos atletas: escala **1–3** (antigos registros podem ter nível 4–5, tratados com `.clamp(1,3)`)
- Apenas o **backend** está versionado no GitHub (`peladatop_app`). O mobile (`mobile/`) não é commitado
- Existe uma versão DEV separada em `~/peladatop_claudecode` — alterações no mobile devem ser replicadas manualmente
- Flutter SDK: **3.19.6** — restringe versões de alguns packages (ex: `screenshot ^2.x`, não `^3.x`)
- Ao adicionar colunas ao banco em produção, rodar `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` **nos dois bancos** (sábado e quinta) para não quebrar o backend compartilhado
