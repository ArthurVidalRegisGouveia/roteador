# roteador


Para iniciar o cenario teste vocês devem executar o seguinte comando em seu computdaor.

**Para iniciar este cenário, abra três terminais separados e execute os seguintes comandos:**

*   **Terminal 1 (Roteador A):**
    ```bash
    python roteador.py -p 5000 -f config_A.csv --network 10.0.0.0/24
    ```
*   **Terminal 2 (Roteador B):**
    ```bash
    python roteador.py -p 5001 -f config_B.csv --network 10.0.1.0/24
    ```
*   **Terminal 3 (Roteador C):**
    ```bash
    python roteador.py -p 5002 -f config_C.csv --network 10.0.2.0/23
    ```