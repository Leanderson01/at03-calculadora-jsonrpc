"""
Servidor da calculadora via JSON-RPC 2.0 sobre HTTP POST.

Implementado "na mão" com http.server para mostrar cada etapa do protocolo:
  1. ler o corpo do POST;
  2. converter o JSON (erro -32700 se não for JSON);
  3. validar o envelope: jsonrpc == "2.0", method, params, id (erro -32600);
  4. achar o método (erro -32601) e conferir os parâmetros (erro -32602);
  5. responder {"jsonrpc": "2.0", "result": ..., "id": ...}
     ou        {"jsonrpc": "2.0", "error": {"code": ..., "message": ...}, "id": ...}.

Códigos customizados (faixa -32000 a -32099, reservada para o servidor):
  -32000  divisão por zero
  -32001  expressão inválida

Exemplo de requisição:
  {"jsonrpc": "2.0", "method": "soma", "params": [10, 15], "id": 1}
"""

import argparse  # lê host e porta da linha de comando
import json  # converte entre texto JSON e dicionários Python
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # servidor HTTP da biblioteca padrão, uma thread por requisição

from expressao import ErroExpressao, avaliar, executor_local  # parser próprio (sem eval)

PARSE_ERROR = -32700  # o corpo não é um JSON válido
INVALID_REQUEST = -32600  # o JSON não é um request JSON-RPC válido
METHOD_NOT_FOUND = -32601  # o método pedido não existe
INVALID_PARAMS = -32602  # parâmetros errados para o método
DIVISAO_POR_ZERO = -32000  # código do servidor para divisão por zero
EXPRESSAO_INVALIDA = -32001  # código do servidor para expressão mal formada


class ErroRPC(Exception):  # erro que vira o campo "error" da resposta
    def __init__(self, codigo, mensagem):  # guarda código e mensagem do erro
        super().__init__(mensagem)  # inicializa a exceção com a mensagem
        self.codigo = codigo  # código numérico JSON-RPC
        self.mensagem = mensagem  # texto legível do erro


def numero(valor):  # valida que um parâmetro é número
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):  # bool é subclasse de int em Python, por isso é excluído
        raise ErroRPC(INVALID_PARAMS, f"Parâmetro não numérico: {valor!r}")  # parâmetro inválido
    return float(valor)  # devolve sempre como float


def operacao_basica(nome):  # fábrica dos quatro métodos básicos
    def metodo(params):  # recebe os "params" do request
        if isinstance(params, dict):  # params por nome: {"a": 10, "b": 15}
            if set(params) != {"a", "b"}:  # precisa exatamente de a e b
                raise ErroRPC(INVALID_PARAMS, f"{nome} espera os parâmetros 'a' e 'b'")  # parâmetros errados
            a, b = params["a"], params["b"]  # extrai os operandos
        elif isinstance(params, list) and len(params) == 2:  # params por posição: [10, 15]
            a, b = params  # extrai os operandos
        else:  # qualquer outro formato
            raise ErroRPC(INVALID_PARAMS, f"{nome} espera dois números: [a, b]")  # parâmetros errados
        try:  # a divisão pode falhar
            return executor_local(nome, numero(a), numero(b))  # calcula e devolve o resultado
        except ZeroDivisionError:  # b == 0 na divisão
            raise ErroRPC(DIVISAO_POR_ZERO, "Divisão por zero")  # vira erro JSON-RPC, o servidor continua no ar
    return metodo  # devolve o método pronto


def calcular_expressao(params):  # Modo B: o servidor calcula a expressão inteira
    if isinstance(params, dict) and set(params) == {"expr"}:  # params por nome: {"expr": "..."}
        expr = params["expr"]  # extrai a expressão
    elif isinstance(params, list) and len(params) == 1:  # params por posição: ["..."]
        expr = params[0]  # extrai a expressão
    else:  # qualquer outro formato
        raise ErroRPC(INVALID_PARAMS, "calcular_expressao espera um parâmetro: [expr]")  # parâmetros errados
    if not isinstance(expr, str):  # a expressão precisa ser texto
        raise ErroRPC(INVALID_PARAMS, "A expressão deve ser uma string")  # parâmetro inválido
    try:  # o parser e o cálculo podem falhar
        return avaliar(expr, executor_local)  # parser + executor local
    except ZeroDivisionError:  # divisão por zero dentro da expressão
        raise ErroRPC(DIVISAO_POR_ZERO, "Divisão por zero")  # erro do servidor
    except ErroExpressao as e:  # expressão mal formada
        raise ErroRPC(EXPRESSAO_INVALIDA, f"Expressão inválida: {e}")  # erro do servidor


METODOS = {  # tabela de despacho: nome do método JSON-RPC -> função Python
    "soma": operacao_basica("soma"),  # soma(a, b)
    "subtracao": operacao_basica("subtracao"),  # subtracao(a, b)
    "multiplicacao": operacao_basica("multiplicacao"),  # multiplicacao(a, b)
    "divisao": operacao_basica("divisao"),  # divisao(a, b)
    "calcular_expressao": calcular_expressao,  # calcular_expressao(expr)
}  # fim da tabela


def resposta_erro(codigo, mensagem, id_requisicao):  # monta o envelope de erro
    return {"jsonrpc": "2.0", "error": {"code": codigo, "message": mensagem}, "id": id_requisicao}  # formato da especificação


def processar(corpo):  # recebe o corpo cru do POST e devolve o dicionário de resposta (ou None)
    try:  # primeiro passo: o corpo precisa ser JSON
        requisicao = json.loads(corpo)  # converte texto em objeto Python
    except (json.JSONDecodeError, UnicodeDecodeError):  # não é JSON
        return resposta_erro(PARSE_ERROR, "Parse error: corpo não é JSON válido", None)  # id é null porque não deu para lê-lo

    if not isinstance(requisicao, dict):  # o request deve ser um objeto JSON
        return resposta_erro(INVALID_REQUEST, "Invalid Request: esperado um objeto JSON", None)  # envelope inválido
    id_requisicao = requisicao.get("id")  # id usado para casar resposta com requisição
    if requisicao.get("jsonrpc") != "2.0":  # a versão é obrigatória e precisa ser "2.0"
        return resposta_erro(INVALID_REQUEST, "Invalid Request: campo 'jsonrpc' deve ser \"2.0\"", id_requisicao)  # envelope inválido
    if not isinstance(requisicao.get("method"), str):  # method é obrigatório e é string
        return resposta_erro(INVALID_REQUEST, "Invalid Request: campo 'method' ausente", id_requisicao)  # envelope inválido
    if "params" in requisicao and not isinstance(requisicao["params"], (list, dict)):  # params, se vier, é lista ou objeto
        return resposta_erro(INVALID_REQUEST, "Invalid Request: 'params' deve ser lista ou objeto", id_requisicao)  # envelope inválido
    if "id" in requisicao and (isinstance(id_requisicao, bool) or not isinstance(id_requisicao, (str, int, float, type(None)))):  # id só pode ser string, número ou null
        return resposta_erro(INVALID_REQUEST, "Invalid Request: 'id' inválido", None)  # envelope inválido

    metodo = METODOS.get(requisicao["method"])  # procura o método na tabela de despacho
    try:  # executa o método
        if metodo is None:  # não existe
            raise ErroRPC(METHOD_NOT_FOUND, f"Method not found: {requisicao['method']}")  # método desconhecido
        resultado = metodo(requisicao.get("params", []))  # chama a função com os parâmetros
    except ErroRPC as e:  # qualquer erro previsto do protocolo ou da calculadora
        if "id" not in requisicao:  # notificação: o cliente não quer resposta, nem de erro
            return None  # nada a responder
        return resposta_erro(e.codigo, e.mensagem, id_requisicao)  # envelope de erro

    if "id" not in requisicao:  # notificação (request sem id)
        return None  # pela especificação, o servidor não responde notificações
    return {"jsonrpc": "2.0", "result": resultado, "id": id_requisicao}  # envelope de sucesso


class TratadorJSONRPC(BaseHTTPRequestHandler):  # trata cada requisição HTTP recebida
    def do_POST(self):  # chamado pelo http.server para cada POST
        tamanho = int(self.headers.get("Content-Length", 0))  # quantos bytes o corpo tem
        corpo = self.rfile.read(tamanho)  # lê exatamente o corpo da requisição
        resposta = processar(corpo)  # aplica o protocolo JSON-RPC
        print(f"    recebido: {corpo.decode('utf-8', 'replace')}  |  resposta: {resposta}")  # mostra a troca no console
        if resposta is None:  # notificação: não há corpo de resposta
            self.send_response(204)  # 204 No Content
            self.end_headers()  # finaliza os cabeçalhos
            return  # termina o tratamento
        dados = json.dumps(resposta, ensure_ascii=False).encode("utf-8")  # serializa a resposta em bytes UTF-8
        self.send_response(200)  # JSON-RPC sobre HTTP responde 200 mesmo com "error" no corpo
        self.send_header("Content-Type", "application/json; charset=utf-8")  # informa que o corpo é JSON
        self.send_header("Content-Length", str(len(dados)))  # tamanho do corpo em bytes
        self.end_headers()  # finaliza os cabeçalhos
        self.wfile.write(dados)  # envia o corpo da resposta

    def do_GET(self):  # GET não faz parte deste serviço
        self.send_error(405, "Use POST com um request JSON-RPC 2.0")  # 405 Method Not Allowed

    def log_message(self, formato, *args):  # silencia o log padrão do http.server
        pass  # o do_POST já imprime o que interessa


def main():  # ponto de entrada do servidor
    parser = argparse.ArgumentParser(description="Servidor da calculadora via JSON-RPC 2.0")  # define os argumentos
    parser.add_argument("--host", default="localhost", help="endereço onde escutar")  # host padrão
    parser.add_argument("--porta", type=int, default=5002, help="porta HTTP (padrão 5002)")  # porta fixa do projeto
    args = parser.parse_args()  # lê os argumentos digitados

    servidor = ThreadingHTTPServer((args.host, args.porta), TratadorJSONRPC)  # cria o servidor HTTP ligado ao tratador
    print(f"Servidor JSON-RPC ouvindo em http://{args.host}:{args.porta}/ (Ctrl+C para sair)")  # avisa que está pronto
    try:  # laço principal; Ctrl+C encerra
        servidor.serve_forever()  # atende requisições indefinidamente
    except KeyboardInterrupt:  # o usuário apertou Ctrl+C
        print("\nEncerrando servidor.")  # mensagem de saída
    finally:  # sempre executa
        servidor.server_close()  # libera a porta


if __name__ == "__main__":  # só executa main() quando o arquivo é rodado diretamente
    main()  # inicia o servidor
