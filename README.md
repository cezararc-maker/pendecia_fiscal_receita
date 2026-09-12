# pendecia_fiscal_receita

Automação **local** em Python + Playwright para consultar, uma empresa por vez, pendências fiscais no Portal de Serviços da Receita Federal, preservando a integração com uma planilha Excel `.xlsm`.

> O código fica no GitHub. A execução autenticada fica exclusivamente no Windows do usuário. Certificados, senhas, PINs, cookies/sessões, planilhas reais, relatórios fiscais e evidências autenticadas **não** devem ser enviados ao repositório.

## Estado atual

O repositório estava completamente vazio em 11/09/2026. Esta branch cria a primeira base Python a partir dos requisitos funcionais fornecidos. Ainda não foi possível comparar a implementação com o protótipo JavaScript nem validar o mapeamento real da planilha porque esses artefatos não estavam no GitHub.

### Arquivos do protótipo ainda necessários

Disponibilize, sem dados sensíveis:

1. o `worker.mjs` usado no protótipo anterior;
2. o código-fonte anterior da pasta `pendencias-fiscais-prototipo`;
3. uma cópia **sanitizada** de `Controle_Folha_Cezar_Prototipo_Pendencias_v1.xlsm`, preservando estrutura, nomes de abas, cabeçalhos, fórmulas, VBA e botões, mas removendo empresas, CNPJs, resultados e caminhos reais.

A planilha real não deve ser versionada.

## O que foi implementado nesta primeira migração

- Python 3.11+ com Playwright assíncrono.
- Fila apenas para registros explicitamente identificados como `CNPJ`; CPF e CAEPF são ignorados pela automação.
- Validação dos dígitos verificadores do CNPJ antes de entrar na fila.
- Integração Excel via **COM/pywin32**, sem regravar a `.xlsm` por bibliotecas que possam remover VBA, botões ou recursos do arquivo.
- Estado persistente local em SQLite, inclusive resultados concluídos ainda não sincronizados com o Excel.
- Comandos `pause`, `resume`, `stop` e `status`; pausa/interrupção ocorrem em ponto seguro antes da próxima empresa.
- Intervalo mínimo de 40 segundos contado a partir do último envio de representação e aplicado **antes** da próxima empresa.
- Localizador do campo como `input[...]`, evitando o `br-select` externo.
- Botão submit delimitado exatamente por `button[type='submit'].br-button.primary.block.margin-5`.
- Sequência crítica de Procurador: clique na opção → `Tab` → 300 ms → `Tab` → 300 ms → `Space`, sem `focus()`, `evaluate()` ou diagnóstico entre as ações.
- Nenhum segundo clique cego no botão depois da sequência de teclado.
- Confirmação separada da ação: só aceita a representação após ler o CNPJ na área de **Dados cadastrais** e compará-lo ao solicitado.
- Se aparecer outro CNPJ ou não houver confirmação, o processamento é interrompido para evitar atribuir dados à empresa errada.
- Resultado só é aceito quando aparece marcador explícito de “sem pendências” ou “com pendências”.
- Quando há pendências, o processamento só conclui se o relatório for efetivamente baixado e o caminho local for registrado.
- Logs JSONL locais com horário, empresa, etapa, duração, código de erro e erro original; screenshots de falha ficam apenas em `.runtime/evidence`.
- CI limitada a testes unitários/estáticos, sem instalar navegador e sem acessar o Portal da Receita.

## O que ainda depende do protótipo/validação local

Três seletores não devem ser inventados sem observar o portal autenticado real:

- `sidebar_toggle_selector`: controle no cabeçalho que abre a barra lateral de representação;
- `identity_scope_selector`: opcional, para tornar ainda mais precisa a área de dados cadastrais (há fallback por título “Dados cadastrais”);
- `report_download_selector`: botão/link exato do relatório (há fallback conservador por nome acessível).

Os textos reais que identificam “com pendências” e “sem pendências” também precisam ser confirmados numa execução controlada.

## Instalação no Windows

No PowerShell, dentro do clone do repositório:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Por padrão o exemplo usa o Microsoft Edge (`browser_channel = "msedge"`), portanto não é obrigatório instalar o Chromium do Playwright. Se optar por Chromium, ajuste a configuração e execute `playwright install chromium`.

Copie a configuração:

```powershell
Copy-Item config.example.toml config.local.toml
```

Edite `config.local.toml` com o caminho da planilha e, após analisarmos a cópia sanitizada, os nomes reais da aba/cabeçalhos. O arquivo local é ignorado pelo Git.

## Diagnóstico antes da primeira empresa

O login, certificado digital e desafios são feitos manualmente por você no navegador aberto pelo Playwright.

```powershell
python -m receita_automacao --config config.local.toml probe
```

`probe` **não representa nenhuma empresa**. Ele informa apenas quantos elementos relevantes estão visíveis e se os seletores pendentes já foram configurados.

Os diagnósticos distinguem, entre outros:

- campo CNPJ não encontrado;
- seletor/ opção Procurador não localizada de forma única;
- sequência de teclas enviada;
- Representar acionado, mas CNPJ cadastral não confirmado;
- CNPJ cadastral diferente do solicitado;
- representação confirmada, porém análise não carregada;
- controle/erro no download do relatório;
- tempo excedido aguardando autenticação manual.

## Primeiro teste controlado

Somente depois de revisar a planilha sanitizada e completar os seletores pendentes:

```powershell
python -m receita_automacao --config config.local.toml run --limit 1
```

Em outro PowerShell, é possível acompanhar/controlar:

```powershell
python -m receita_automacao --config config.local.toml status
python -m receita_automacao --config config.local.toml pause
python -m receita_automacao --config config.local.toml resume
python -m receita_automacao --config config.local.toml stop
```

Falhas do portal deixam o job em `failed` e interrompem o lote. Depois de analisar/corrigir a causa, uma nova tentativa precisa ser explícita:

```powershell
python -m receita_automacao --config config.local.toml run --limit 1 --retry-failed
```

## Testes automáticos

```powershell
pytest -q
ruff check src tests
```

Os testes atuais cobrem validação de CNPJ, exclusão de CAEPF da fila automática, persistência de resultados/controle e, principalmente, a ordem exata da sequência `Procurador → Tab → 300 ms → Tab → 300 ms → Space`.

## O que significa “validado” neste projeto

Há três níveis distintos:

1. **Implementado:** código existe e está versionado.
2. **Testado automaticamente:** comportamento isolado foi exercitado por testes sem acesso ao portal.
3. **Validado no portal:** somente após execução local, com navegador autenticado, confirmação da troca real de CNPJ e carregamento do resultado fiscal.

Esta primeira versão **não deve ser considerada validada no portal** até o teste local controlado com uma empresa.
