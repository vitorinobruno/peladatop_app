# Migrações para aplicar na versão de produção

Este arquivo documenta todas as alterações validadas na versão de testes.
Pode ser usado diretamente como prompt para o Claude Code na versão oficial:
> "Leia o arquivo MIGRAR_PARA_PRODUCAO.md e aplique todas as alterações descritas."

---

## 1. Nível dos atletas: escala 1–3 (era 1–5)

**Arquivo:** `mobile/.../lib/screens/atletas/atletas_screen.dart`

No widget `_FormAtletaState`, método `initState`:
- Alterar o valor padrão de `nivel` de `3` para `2`
- Aplicar `.clamp(1, 3)` ao carregar o nível do atleta existente (para atletas com nível 4 ou 5 cadastrados anteriormente)

```dart
// antes
nivel = widget.atleta?.nivel ?? 3;

// depois
nivel = widget.atleta?.nivel.clamp(1, 3) ?? 2;
```

No widget `Slider` de nível:
```dart
// antes
max: 5,
divisions: 4,

// depois
max: 3,
divisions: 2,
```

---

## 2. Histórico de peladas: ordenação e filtro por data

### 2a. Backend — `GET /peladas`

**Arquivo:** `backend/main.py`

Substituir o endpoint `GET /peladas` pelo seguinte (aceita query params opcionais
`data_inicio` e `data_fim`, retorna ordenado por data decrescente, inclui `status` e `campeao`):

```python
@app.get("/peladas")
def listar_peladas(
    session: Session = Depends(get_session),
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
):
    query = select(Pelada).order_by(col(Pelada.data).desc())
    if data_inicio:
        query = query.where(Pelada.data >= data_inicio)
    if data_fim:
        query = query.where(Pelada.data <= data_fim)
    peladas = session.exec(query).all()

    return [
        {
            "id": p.id,
            "data": p.data,
            "local": p.local,
            "status": p.status,
            "campeao": p.campeao,
        }
        for p in peladas
    ]
```

Verificar que `col` está importado: `from sqlmodel import col`

### 2b. Mobile — modelo `Pelada`

**Arquivo:** `mobile/.../lib/models/pelada.dart`

Adicionar campos `status` e `campeao`:

```dart
class Pelada {
  final int id;
  final String data;
  final String local;
  final int maxAtletas;
  final String status;      // novo
  final String? campeao;    // novo

  Pelada({
    required this.id,
    required this.data,
    required this.local,
    required this.maxAtletas,
    required this.status,
    this.campeao,
  });

  factory Pelada.fromJson(Map<String, dynamic> json) {
    return Pelada(
      id: json['id'],
      data: json['data'],
      local: json['local'],
      maxAtletas: json['max_atletas'] ?? 30,
      status: json['status'] ?? 'planejada',
      campeao: json['campeao'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      "data": data,
      "local": local,
    };
  }
}
```

### 2c. Mobile — serviço `PeladaService`

**Arquivo:** `mobile/.../lib/services/pelada_service.dart`

Substituir o método `getPeladas`:

```dart
Future<List<Pelada>> getPeladas({DateTime? dataInicio, DateTime? dataFim}) async {
  final params = <String, String>{};
  if (dataInicio != null) params['data_inicio'] = dataInicio.toIso8601String().substring(0, 10);
  if (dataFim != null) params['data_fim'] = dataFim.toIso8601String().substring(0, 10);
  final uri = Uri.parse("$baseUrl/peladas").replace(queryParameters: params.isEmpty ? null : params);
  final res = await http.get(uri);
  final data = jsonDecode(utf8.decode(res.bodyBytes)) as List;
  return data.map((e) => Pelada.fromJson(e)).toList();
}
```

### 2d. Mobile — tela `PeladasScreen`

**Arquivo:** `mobile/.../lib/screens/peladas/peladas_screen.dart`

Substituir completamente a classe `_PeladasBodyState` e o widget `_CardPelada` pelos
equivalentes do arquivo `mobile/.../lib/screens/peladas/peladas_screen.dart` da versão
de testes. As mudanças são:

- `_PeladasBodyState`: adiciona `_dataInicio`, `_dataFim`, `_selecionarFiltroData()`,
  `_limparFiltro()`, e passa os parâmetros de filtro ao `getPeladas()`. A build exibe
  botões de filtro/limpar no cabeçalho da lista e o período selecionado.
- `_CardPelada`: exibe status da pelada (Planejada / Em andamento / Finalizada) e nome
  do campeão quando finalizada, usando `isThreeLine: true`.

---

## 3. Tela de Times: sorteio automático + exportação WhatsApp

**Arquivo:** `mobile/.../lib/screens/times/times_screen.dart`

Substituir o arquivo completo pelo da versão de testes. As adições são:

### 3a. Import
```dart
import 'dart:math' show Random, min;
import 'package:url_launcher/url_launcher.dart';
```

### 3b. Algoritmo de sorteio `_sortearTimes()`

Composição por time: `{ "zagueiro": 3, "volante": 1, "ala": 3, "atacante": 2 }`.

Lógica em 4 passos:
1. **Snake draft por posição** (sem cap de atletas): distribui todos os atletas de cada posição com início aleatório por rodada, diferença máxima de 1 por posição entre os times
2. **Passe de posições fora da composição** (ex: goleiros): aloca no time com menos atletas com desempate aleatório
3. **Balanceamento de tamanho**: move atletas do time maior para o menor (priorizando posições com excesso) até diferença ≤ 1
4. **Balanceamento de força** (soma de níveis): troca pares de mesma posição entre o time mais forte e o mais fraco até diferença ≤ 1

### 3c. Exportação WhatsApp `_compartilharWhatsApp()`

Gera texto formatado com emoji de cor por time:
- ⚪ Branco, 🔵 Azul, 🟠 Laranja, 🟢 Verde

Abre via `url_launcher`: `https://wa.me/?text=<texto_codificado>`

### 3d. UI
- Botão "Sortear times automaticamente" (OutlinedButton com ícone shuffle) entre o seletor de quantidade e os cards de time
- Botão "WhatsApp" ao lado do "Salvar Times" (visível quando algum time tem atletas)
- Ícone de compartilhar no AppBar
- Cards de times exibem atletas agrupados por posição

---

## 4. Salvar times: comportamento por status dos jogos

**Arquivo:** `backend/main.py` — endpoint `POST /peladas/{pelada_id}/times`

Substituir a lógica atual pelos 3 cenários abaixo:

| Situação | Comportamento |
|---|---|
| Sem jogos gerados | Apaga times existentes e recria do zero |
| Jogos gerados, **nenhum iniciado** | Apaga jogos + times e recria do zero |
| **Algum jogo iniciado ou finalizado** | Apenas atualiza atletas dos times existentes |

```python
@app.post("/peladas/{pelada_id}/times")
def criar_times(
    pelada_id: int,
    times: list[TimeCreate],
    session: Session = Depends(get_session)
):
    jogos_existentes = session.exec(
        select(Jogo).where(Jogo.pelada_id == pelada_id)
    ).all()

    times_existentes = session.exec(
        select(Time).where(Time.pelada_id == pelada_id)
    ).all()

    algum_jogo_iniciado = any(
        j.status in ("em_andamento", "finalizado") for j in jogos_existentes
    )

    if jogos_existentes and algum_jogo_iniciado:
        # Algum jogo já foi iniciado: apenas atualiza atletas dos times existentes
        for i, time_existente in enumerate(times_existentes):
            if i >= len(times):
                break
            t = times[i]
            time_existente.nome = t.nome
            time_existente.cor = t.cor
            session.add(time_existente)

            session.exec(
                delete(TimeAtleta).where(TimeAtleta.time_id == time_existente.id)
            )
            for atleta_id in t.atletas_ids:
                session.add(TimeAtleta(
                    time_id=time_existente.id,
                    atleta_id=atleta_id
                ))

        session.commit()
        return {"msg": "Times atualizados com sucesso"}

    if jogos_existentes:
        # Jogos gerados mas nenhum iniciado: apaga jogos e times, recria tudo
        for j in jogos_existentes:
            session.exec(delete(Partida).where(Partida.jogo_id == j.id))
            session.delete(j)
        session.commit()

    # Sem jogos (ou após limpeza): recria times do zero
    for t in times_existentes:
        session.exec(
            delete(TimeAtleta).where(TimeAtleta.time_id == t.id)
        )
        session.delete(t)
    session.commit()

    for t in times:
        time = Time(pelada_id=pelada_id, nome=t.nome, cor=t.cor)
        session.add(time)
        session.commit()
        session.refresh(time)

        for atleta_id in t.atletas_ids:
            session.add(TimeAtleta(time_id=time.id, atleta_id=atleta_id))

    session.commit()
    return {"msg": "Times salvos com sucesso"}
```

---

## 5. Tempo máximo de partida: 60 → 80 minutos

**Arquivo:** `mobile/.../lib/screens/jogos/jogos_screen.dart`

No widget `Slider` de tempo por partida:
```dart
// antes
max: 60,

// depois
max: 80,
```
