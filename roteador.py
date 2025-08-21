# -*- coding: utf-8 -*-

import csv
import ipaddress
import json
import threading
import time
from argparse import ArgumentParser
import requests
from flask import Flask, jsonify, request

class Router:
    """
    Representa um roteador que executa o algoritmo de Vetor de Distância.
    """

    def __init__(self, my_address, neighbors, my_network, update_interval=1):
        """
        Inicializa o roteador.

        :param my_address: O endereço (ip:porta) deste roteador.
        :param neighbors: Um dicionário contendo os vizinhos diretos e o custo do link.
                          Ex: {'127.0.0.1:5001': 5, '127.0.0.1:5002': 10}
        :param my_network: A rede que este roteador administra diretamente.
                           Ex: '10.0.1.0/24'
        :param update_interval: O intervalo em segundos para enviar atualizações, o tempo que o roteador espera
                                antes de enviar atualizações para os vizinhos.        """
        self.my_address = my_address
        self.neighbors = neighbors
        self.my_network = my_network
        self.update_interval = update_interval

        # --- Inicializa a tabela de roteamento ---
        self.routing_table = {}

        # Rota para a rede local (custo 0, próximo salto = eu)
        self.routing_table[self.my_network] = {
            "cost": 0,
            "next_hop": self.my_address
        }

        # Rotas para os vizinhos diretos
        for neighbor, cost in self.neighbors.items():
            self.routing_table[neighbor] = {
                "cost": cost,
                "next_hop": neighbor
            }

        print("Tabela de roteamento inicial:")
        print(json.dumps(self.routing_table, indent=4))

        # Inicia o processo de atualização periódica em uma thread separada
        self._start_periodic_updates()

    def _start_periodic_updates(self):
        """Inicia uma thread para enviar atualizações periodicamente."""
        thread = threading.Thread(target=self._periodic_update_loop)
        thread.daemon = True
        thread.start()

    def _periodic_update_loop(self):
        """Loop que envia atualizações de roteamento em intervalos regulares."""
        while True:
            time.sleep(self.update_interval)
            print(f"[{time.ctime()}] Enviando atualizações periódicas para os vizinhos...")
            try:
                self.send_updates_to_neighbors()
            except Exception as e:
                print(f"Erro durante a atualização periódica: {e}")

    def send_updates_to_neighbors(self):
        """
        Envia a tabela de roteamento (com sumarização) para todos os vizinhos.
        """

        try:
            all_networks = []
            mapping = {}

            for net_str, info in self.routing_table.items():
                try:
                    net = ipaddress.ip_network(net_str, strict=False)
                    all_networks.append(net)
                    mapping[net] = info
                except ValueError:
                    # caso não seja uma rede válida, manda como está
                    mapping[net_str] = info

            summarized = list(ipaddress.collapse_addresses(all_networks))

            tabela_para_enviar = {}
            for net in summarized:
                if net in mapping:
                    tabela_para_enviar[str(net)] = mapping[net]
                else:
                    # se foi colapsado, manda custo e next_hop genéricos
                    tabela_para_enviar[str(net)] = {
                        "cost": min(mapping[n].get("cost", 9999) for n in mapping if
                                    isinstance(n, ipaddress._BaseNetwork) and n.subnet_of(net)),
                        "next_hop": "SUMARIZED"
                    }

        except Exception as e:
            print(f"Erro ao sumarizar rotas: {e}")
            tabela_para_enviar = dict(self.routing_table)

        payload = {
            "sender_address": self.my_address,
            "routing_table": tabela_para_enviar
        }

        for neighbor_address in self.neighbors:
            url = f'http://{neighbor_address}/receive_update'
            try:
                print(f"Enviando tabela (sumarizada) para {neighbor_address}")
                requests.post(url, json=payload, timeout=5)
            except requests.exceptions.RequestException as e:
                print(f"Não foi possível conectar ao vizinho {neighbor_address}. Erro: {e}")


# --- API Endpoints ---
app = Flask(__name__)
router_instance = None


@app.route('/routes', methods=['GET'])
def get_routes():
    """Endpoint para visualizar a tabela de roteamento atual (organizada)."""
    if not router_instance:
        return jsonify({"error": "Roteador não inicializado"}), 500

    tabela_formatada = []
    for rede, info in router_instance.routing_table.items():
        tabela_formatada.append({
            "destino": rede,
            "custo": info.get("cost", "-"),
            "proximo_salto": info.get("next_hop", "-")
        })

    response = {
        "roteador": {
            "meu_endereco": router_instance.my_address,
            "minha_rede": router_instance.my_network,
            "intervalo_atualizacao": router_instance.update_interval
        },
        "vizinhos": [
            {"endereco": vizinho, "custo_link": custo}
            for vizinho, custo in router_instance.neighbors.items()
        ],
        "tabela_de_roteamento": tabela_formatada
    }

    return jsonify(response), 200


@app.route('/receive_update', methods=['POST'])
def receive_update():
    """Endpoint que recebe atualizações de roteamento de um vizinho."""
    if not request.json:
        return jsonify({"error": "Invalid request"}), 400

    update_data = request.json
    sender_address = update_data.get("sender_address")
    sender_table = update_data.get("routing_table")

    if not sender_address or not isinstance(sender_table, dict):
        return jsonify({"error": "Missing sender_address or routing_table"}), 400

    print(f"Recebida atualização de {sender_address}:")
    print(json.dumps(sender_table, indent=4))

    update_happened = False
    link_cost = router_instance.neighbors.get(sender_address)

    if link_cost is None:
        return jsonify({"error": "Remetente não é vizinho direto"}), 400

    #  Algoritmo Bellman-Ford
    for network, info in sender_table.items():
        received_cost = info["cost"]
        new_cost = link_cost + received_cost

        if network not in router_instance.routing_table:
            router_instance.routing_table[network] = {
                "cost": new_cost,
                "next_hop": sender_address
            }
            update_happened = True
        else:
            current_entry = router_instance.routing_table[network]
            if new_cost < current_entry["cost"] or current_entry["next_hop"] == sender_address:
                router_instance.routing_table[network] = {
                    "cost": new_cost,
                    "next_hop": sender_address
                }
                update_happened = True

    if update_happened:
        print("Tabela de roteamento atualizada:")
        print(json.dumps(router_instance.routing_table, indent=4))

    return jsonify({"status": "success", "message": "Update received"}), 200


# --- MAIN ---
if __name__ == '__main__':
    parser = ArgumentParser(description="Simulador de Roteador com Vetor de Distância")
    parser.add_argument('-p', '--port', type=int, default=5000, help="Porta para executar o roteador.")
    parser.add_argument('-f', '--file', type=str, required=True, help="Arquivo CSV de configuração de vizinhos.")
    parser.add_argument('--network', type=str, required=True, help="Rede administrada por este roteador (ex: 10.0.1.0/24).")
    parser.add_argument('--interval', type=int, default=10, help="Intervalo de atualização periódica em segundos.")
    args = parser.parse_args()

    # Leitura do arquivo de configuração de vizinhos
    neighbors_config = {}
    try:
        with open(args.file, mode='r') as infile:
            reader = csv.DictReader(infile)
            for row in reader:
                neighbors_config[row['vizinho']] = int(row['custo'])
    except FileNotFoundError:
        print(f"Erro: Arquivo de configuração '{args.file}' não encontrado.")
        exit(1)
    except (KeyError, ValueError) as e:
        print(f"Erro no formato do arquivo CSV: {e}. Verifique as colunas 'vizinho' e 'custo'.")
        exit(1)

    my_full_address = f"127.0.0.1:{args.port}"
    print("--- Iniciando Roteador ---")
    print(f"Endereço: {my_full_address}")
    print(f"Rede Local: {args.network}")
    print(f"Vizinhos Diretos: {neighbors_config}")
    print(f"Intervalo de Atualização: {args.interval}s")
    print("--------------------------")

    router_instance = Router(
        my_address=my_full_address,
        neighbors=neighbors_config,
        my_network=args.network,
        update_interval=args.interval
    )

    # Inicia o servidor Flask
    app.run(host='0.0.0.0', port=args.port, debug=False)