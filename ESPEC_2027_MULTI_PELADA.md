# PeladaTop 2027 — Multi-pelada (Segunda, Quinta e Sábado)

> **Status:** especificação em rascunho. Nada implementado.
> **Objetivo:** atender a nova pelada de segunda-feira sem criar um 3º serviço,
> unificando as três peladas em **1 backend + 1 app**, com dados totalmente isolados.

---

## 1. Contexto

| Hoje (2026) | Problema |
|---|---|
| 2 serviços no Render (`peladatop-app`, `peladatop-app-quinta`) | Um 3º serviço para a segunda multiplica custo/limites do plano |
| 2 bancos PostgreSQL | Toda migração (`ALTER TABLE`) precisa ser rodada em cada banco |
| 2 flavors Android (`sabado`, `quinta`) | Um APK por pelada; um 3º flavor para a segunda |

**Requisitos (definidos pelo organizador):**
1. Um único serviço no Render: se um dia o plano virar pago, paga-se só 1.
2. Um único app: o usuário escolhe a pelada.
3. **Nenhuma comunicação entre peladas**: atletas, presenças, times, jogos, estatísticas, títulos e rankings são 100% separados.
4. A interface é a mesma para todas, como hoje.

---

## 2. Decisão de arquitetura: isolamento dos dados

Três opções avaliadas:

| | A) 3 bancos separados | B) 1 banco, coluna `grupo_id` | **C) 1 banco, 1 schema por pelada** |
|---|---|---|---|
| Bancos no Render | 3 | 1 | **1** |
| Isolamento | Total | Depende de nunca esquecer um filtro | **Total** (tabelas fisicamente separadas) |
| Mudança no código do backend | Pequena (engine por pelada) | **Grande**: as 47 queries de `main.py` ganham filtro por grupo | **Pequena**: queries continuam iguais |
| Migrar os dados de 2026 | Nenhuma | Difícil: IDs de sábado e quinta colidem, exige remapear todas as FKs | **Simples**: `pg_dump` de cada banco → restore no seu schema |
| Migrações futuras | Rodar em 3 bancos | Rodar 1 vez | Rodar 1 vez por schema (script automatiza) |

### ✅ Recomendação: opção C (schema por pelada)

Um único PostgreSQL com os schemas `sabado`, `quinta` e `segunda`, cada um com o conjunto completo de tabelas que existe hoje.
A cada request, o backend define o `search_path` da sessão para o schema da pelada escolhida.

- Isolamento real: uma query sem filtro **não consegue** ler dados de outra pelada.
- O código de negócio (sorteio, classificação, torneio, estatísticas, resenha) não muda.
- Os IDs atuais são preservados, então os links de presença antigos e os registros históricos continuam válidos.

---

## 3. Backend

### 3.1 Identificação da pelada em cada request
A pelada vai **na URL**, não em header, porque o link de presença (`/presenca-link`) é aberto no navegador a partir do WhatsApp e não consegue enviar headers.

```
/{grupo}/atletas
/{grupo}/peladas/{id}/presenca-link
/{grupo}/estatisticas/gols
...
grupo ∈ { sabado, quinta, segunda }
```

- Todos os endpoints atuais passam para um `APIRouter(prefix="/{grupo}")`.
- Uma dependência `get_session(grupo)` valida o grupo contra a lista cadastrada (nunca interpola texto livre no SQL) e executa `SET search_path TO <grupo>` na sessão.
- `GET /grupos` (sem prefixo) lista as peladas disponíveis para a tela de escolha do app.

### 3.2 Cadastro das peladas
Tabela `public.grupo` (ou config estática no código, já que são só 3):

| campo | exemplo |
|---|---|
| `slug` | `segunda` |
| `nome` | `Pelada de Segunda` |
| `dia_semana` | `1` |
| `ativo` | `true` |

### 3.3 Criação de tabelas e migrações
- Startup: para cada grupo, `CREATE SCHEMA IF NOT EXISTS` + `create_all` com `search_path` apontando para o schema.
- Novas colunas: script único `migrar.py` que roda o `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` em todos os schemas. Isso substitui a regra atual de "rodar nos dois bancos".

### 3.4 Compatibilidade com os APKs de 2026
Os apps antigos chamam as rotas sem prefixo. Durante a transição:
- O serviço unificado assume a URL do sábado (`peladatop-app.onrender.com`) e mantém **rotas legadas sem prefixo → schema `sabado`**.
- O serviço da quinta fica no ar até todos atualizarem o app, e depois é desligado.
- As rotas legadas são removidas depois da transição.

---

## 4. App (Flutter)

- **Remover os flavors.** Fica um só app, mantendo o `applicationId` atual do sábado (`com.example.peladatop_mobile`) para os usuários do sábado receberem como atualização. Os usuários da quinta instalam o app novo.
- **Tela de escolha da pelada** no primeiro acesso, com a lista vinda de `GET /grupos`. A escolha fica salva no aparelho (adicionar `shared_preferences`).
- **Trocar de pelada** pelo menu ou AppBar, mostrando sempre o nome da pelada ativa para evitar registrar na pelada errada.
- `ApiConfig`: `baseUrl` fixo + `grupo` selecionado. Os services montam `"$baseUrl/$grupo/..."`.
- **Caches** dos services (`_cache`) com o grupo na chave, ou limpos ao trocar de pelada.
- Ao trocar de pelada: limpar `PeladaProvider.peladaAtiva`.
- **Link de presença do WhatsApp:** `"$baseUrl/$grupo/peladas/{id}/presenca-link"`.
- Card, resultados e resenha passam a mostrar o nome da pelada (ex: "Pelada de Segunda").

---

## 5. Migração dos dados (executar uma vez, antes da virada)

1. Backup completo dos dois bancos atuais (`pg_dump`).
2. No banco unificado: `CREATE SCHEMA sabado; CREATE SCHEMA quinta; CREATE SCHEMA segunda;`
3. Restaurar o dump do sábado no schema `sabado` e o da quinta no schema `quinta` (ajustando o schema de destino no restore).
4. `segunda` começa vazio. Os atletas são cadastrados do zero ou importados via `importar_atletas.py`.
5. Validar as contagens (atletas, peladas, jogos, eventos) e os rankings de cada schema contra o banco original.
6. Corrigir as sequences (`setval`) de cada tabela em cada schema.
7. Publicar o backend, distribuir o APK novo e desligar o serviço e o banco da quinta após a transição.

---

## 6. Fora de escopo
- Qualquer dado compartilhado entre peladas (ex: atleta que joga em duas aparece como dois cadastros independentes).
- Rankings consolidados entre peladas.
- Login/contas de usuário (ver questão em aberto 7.3).

---

## 7. Questões em aberto

1. **Configuração por pelada:** a segunda usa as mesmas cores de time, a mesma composição do sorteio (`3 zag / 1 vol / 3 ala / 2 ata`) e o mesmo tempo padrão? Se algo variar, vira configuração em `grupo`.
2. **Torneio de fim de ano:** fica disponível para as três peladas, cada uma com o seu? (A estrutura atual já permite.)
3. **Acesso:** hoje não há autenticação. Com as três peladas no mesmo app, qualquer pessoa pode abrir e editar outra pelada. Basta a escolha na tela, ou cada pelada deve ter um PIN de administrador para operações de escrita?
4. **Quem usa o app:** só os organizadores, ou também atletas (ex: consultar estatísticas)? Isso influencia a questão 3.
5. **iOS:** o CLAUDE.md cita App Store. Há build iOS em uso que também precisa migrar?
6. **Plano do Render:** conferir os limites atuais do plano gratuito (horas de instância por mês, quantidade e validade de bancos gratuitos) para confirmar a economia e se o banco unificado comporta os três volumes.
7. **Cronograma:** a segunda começa a usar o app quando? A migração da quinta e do sábado pode acontecer depois, já que a segunda nasce direto no modelo novo.

---

## 8. Estimativa de etapas

| # | Etapa | Observação |
|---|---|---|
| 1 | Router com prefixo `/{grupo}` + sessão com `search_path` + `GET /grupos` | Núcleo da mudança |
| 2 | Script de migrações multi-schema + rotas legadas | |
| 3 | App: tela de escolha, `ApiConfig` com grupo, cache por grupo, remoção de flavors | |
| 4 | Ambiente de teste com cópia dos dados de 2026 | Validar antes da virada |
| 5 | Migração de produção + distribuição do APK | Janela fora dos dias de pelada |
