"""
Cliente da calculadora via JSON-RPC 2.0 sobre HTTP POST.

Monta os requests JSON-RPC manualmente (sem biblioteca de RPC), com id
incremental, e trata os campos "result" e "error" da resposta.

Use --verbose para ver o JSON enviado e recebido em cada chamada.
"""

import argparse  # lê host, porta e --verbose da linha de comando
import itertools  # gera a sequência de ids 1, 2, 3...
import json  # formata o JSON no modo --verbose

import requests  # cliente HTTP

from expressao import SIMBOLOS, ErroExpressao, analisar_operacao_simples, avaliar, formatar  # parser próprio


class ErroRemoto(Exception):  # erro devolvido pelo servidor no campo "error"
    def __init__(self, codigo, mensagem):  # guarda código e mensagem
        super().__init__(f"[{codigo}] {mensagem}")  # texto exibido ao usuário
        self.codigo = codigo  # código numérico JSON-RPC


class ClienteJSONRPC:  # encapsula o endpoint e o contador de ids
    def __init__(self, url, verbose=False):  # configura o cliente
        self.url = url  # endereço do servidor, ex.: http://localhost:5002/
        self.verbose = verbose  # se True, imprime o JSON trafegado
        self.ids = itertools.count(1)  # contador de ids: cada request recebe o próximo número
        self.sessao = requests.Session()  # reaproveita a conexão TCP entre chamadas (HTTP keep-alive)

    def chamar(self, metodo, params):  # faz uma chamada JSON-RPC
        requisicao = {"jsonrpc": "2.0", "method": metodo, "params": params, "id": next(self.ids)}  # monta o envelope do request
        if self.verbose:  # modo didático
            print(f"    enviado:  {json.dumps(requisicao, ensure_ascii=False)}")  # mostra o JSON enviado
        http = self.sessao.post(self.url, json=requisicao, timeout=5)  # envia o POST com Content-Type: application/json
        http.raise_for_status()  # erro de transporte (ex.: 404, 500) vira exceção
        resposta = http.json()  # converte o corpo da resposta em dicionário
        if self.verbose:  # modo didático
            print(f"    recebido: {json.dumps(resposta, ensure_ascii=False)}")  # mostra o JSON recebido
        if resposta.get("id") != requisicao["id"]:  # a resposta deve ter o mesmo id do request
            raise ErroRemoto(0, "Resposta com id diferente do request")  # algo errado no servidor
        if "error" in resposta:  # o servidor devolveu erro
            erro = resposta["error"]  # objeto {"code", "message"}
            raise ErroRemoto(erro["code"], erro["message"])  # vira exceção no cliente
        return resposta["result"]  # sucesso: devolve só o resultado


def executor_remoto(cliente):  # cria o executor do Modo A, ligado a este cliente
    def executar(op, a, b):  # chamado pelo parser para cada operação básica
        resultado = cliente.chamar(op, [a, b])  # um request JSON-RPC por operação
        print(f"  → servidor: {op}({formatar(a)}, {formatar(b)}) = {formatar(resultado)}")  # mostra cada chamada remota
        return resultado  # devolve o valor para o parser continuar
    return executar  # o parser recebe essa função como executor


MENU = """
=== Calculadora JSON-RPC ===
1) Operação simples (ex: 10 + 15)
2) Expressão – Modo A (cliente decompõe e chama o servidor por operação)
3) Expressão – Modo B (servidor calcula a expressão inteira)
0) Sair"""  # texto do menu


def main():  # ponto de entrada do cliente
    parser = argparse.ArgumentParser(description="Cliente da calculadora via JSON-RPC 2.0")  # define os argumentos
    parser.add_argument("--host", default="localhost", help="endereço do servidor")  # host padrão
    parser.add_argument("--porta", type=int, default=5002, help="porta do servidor (padrão 5002)")  # porta padrão
    parser.add_argument("--verbose", action="store_true", help="mostra o JSON enviado e recebido")  # modo didático
    args = parser.parse_args()  # lê os argumentos digitados

    cliente = ClienteJSONRPC(f"http://{args.host}:{args.porta}/", args.verbose)  # cria o cliente apontando para o servidor
    print(f"Servidor: {cliente.url}")  # mostra para onde as chamadas vão
    try:  # Ctrl+C encerra
        while True:  # repete o menu até o usuário sair
            print(MENU)  # mostra as opções
            opcao = input("Escolha: ").strip()  # lê a opção digitada
            if opcao == "0":  # sair
                break  # sai do laço
            if opcao not in ("1", "2", "3"):  # opção inexistente
                print("Opção inválida.")  # avisa e mostra o menu de novo
                continue  # volta ao início do laço
            texto = input("Digite: ").strip()  # lê a operação ou expressão
            try:  # erros de entrada, do servidor ou de rede não encerram o programa
                if opcao == "1":  # operação simples
                    op, a, b = analisar_operacao_simples(texto)  # extrai operação e operandos
                    resultado = cliente.chamar(op, [a, b])  # um único request JSON-RPC
                    print(f"{formatar(a)} {SIMBOLOS[op]} {formatar(b)} = {formatar(resultado)}")  # mostra o resultado
                elif opcao == "2":  # Modo A
                    resultado = avaliar(texto, executor_remoto(cliente))  # parser local + um request por operação
                    print(f"Resultado final: {formatar(resultado)}")  # mostra o resultado
                else:  # Modo B
                    resultado = cliente.chamar("calcular_expressao", [texto])  # um request com a expressão inteira
                    print(f"Resultado (calculado no servidor): {formatar(resultado)}")  # mostra o resultado
            except ErroExpressao as e:  # o parser local recusou a entrada
                print(f"Entrada inválida: {e}")  # explica o erro
            except ErroRemoto as e:  # o servidor respondeu com "error"
                print(f"Erro do servidor: {e}")  # mostra código e mensagem
            except requests.RequestException as e:  # servidor fora do ar, timeout etc.
                print(f"Falha de comunicação com o servidor: {e}")  # avisa sem encerrar
    except (KeyboardInterrupt, EOFError):  # Ctrl+C ou fim da entrada
        print()  # pula linha antes de sair
    finally:  # sempre executa
        cliente.sessao.close()  # fecha as conexões abertas pela sessão HTTP
        print("Até logo!")  # despedida


if __name__ == "__main__":  # só executa main() quando o arquivo é rodado diretamente
    main()  # inicia o cliente
