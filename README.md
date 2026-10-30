# AT03 – Calculadora distribuída via JSON-RPC 2.0

Trabalho AT03 de Sistemas Distribuídos (SMD/UFC, 2026). Calculadora remota com **JSON-RPC 2.0 sobre HTTP POST**. É a versão em Python do projeto `rpcKTOR`.

## Paradigma

Chamada de procedimento remoto (RPC) com mensagens JSON. O servidor foi escrito **à mão** sobre `http.server`, sem biblioteca de RPC, para que cada etapa do protocolo apareça no código:

1. ler o corpo do POST;
2. converter o JSON (se falhar: `-32700`);
3. validar o envelope (`jsonrpc` = `"2.0"`, `method`, `params`, `id`) (se falhar: `-32600`);
4. achar o método (se não existir: `-32601`) e conferir os parâmetros (se estiverem errados: `-32602`);
5. responder com `result` ou `error`, repetindo o `id` do pedido.

```json
→ {"jsonrpc": "2.0", "method": "soma", "params": [10, 15], "id": 1}
← {"jsonrpc": "2.0", "result": 25.0, "id": 1}

→ {"jsonrpc": "2.0", "method": "divisao", "params": [5, 0], "id": 2}
← {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Divisão por zero"}, "id": 2}
```

| Código | Significado |
|---|---|
| -32700 | Parse error: o corpo não é JSON |
| -32600 | Invalid Request: envelope inválido |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32000 | Divisão por zero (código do servidor) |
| -32001 | Expressão inválida (código do servidor) |

Métodos: `soma`, `subtracao`, `multiplicacao`, `divisao` (`params` = `[a, b]` ou `{"a":..,"b":..}`) e `calcular_expressao` (`params` = `["expr"]`). Um request sem `id` é uma *notificação*: o servidor executa e responde `204` sem corpo, como manda a especificação.

O cliente monta os requests com `requests`, usa `id` incremental, confere se o `id` da resposta é o mesmo do pedido e trata `result` e `error`.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `servidor.py` | Servidor JSON-RPC sobre `http.server` (todas as linhas comentadas) |
| `cliente.py` | Cliente com menu e `--verbose` (todas as linhas comentadas) |
| `expressao.py` | Parser de expressões (descida recursiva, sem `eval`) |
| `test_expressao.py` | Testes do parser |

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Como executar

```bash
python servidor.py               # http://localhost:5002/
python cliente.py --verbose      # --verbose mostra o JSON enviado e recebido
```

Opções: `--host` e `--porta` nos dois programas.

Exemplo do Modo A com `--verbose`:

```
    enviado:  {"jsonrpc": "2.0", "method": "soma", "params": [10.0, 15.0], "id": 2}
    recebido: {"jsonrpc": "2.0", "result": 25.0, "id": 2}
  → servidor: soma(10, 15) = 25
    enviado:  {"jsonrpc": "2.0", "method": "multiplicacao", "params": [25.0, 4.0], "id": 3}
    recebido: {"jsonrpc": "2.0", "result": 100.0, "id": 3}
  → servidor: multiplicacao(25, 4) = 100
Resultado final: 100
```

Também dá para testar sem o cliente:

```bash
curl -d '{"jsonrpc":"2.0","method":"calcular_expressao","params":["(10+15)*4"],"id":1}' localhost:5002
```

Testes do parser: `python -m pytest -q` (ou `python -m unittest`).

## Captura no Wireshark

1. Interface de loopback: **Adapter for loopback traffic capture** no Windows (Npcap), `lo` no Linux, `lo0` no macOS.
2. Filtro: `tcp.port == 5002`. Para ver só as mensagens HTTP: `tcp.port == 5002 and http`.

O que observar:
- cada chamada é um **POST HTTP** com `Content-Type: application/json` e o envelope JSON-RPC no corpo;
- a resposta é sempre **HTTP 200**: o erro de aplicação vai no campo `error` do corpo, e não no status HTTP. Essa é uma diferença importante em relação ao REST;
- o `id` do request se repete na resposta;
- cada chamada abre a **própria conexão TCP**, com handshake, POST, resposta e FIN: o `http.server` responde em HTTP/1.0 e fecha a conexão depois de cada resposta. No Modo A, isso aparece como um handshake por operação, o que contrasta com o socket, que tem uma conexão só.
