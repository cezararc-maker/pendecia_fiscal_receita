# pendecia_fiscal_receita

Automação local em **Python + Playwright** para consultar pendências fiscais no Portal de Serviços da Receita Federal, preservando a integração já existente com a planilha Excel `.xlsm`.

O código fica no GitHub. A execução autenticada ocorre somente no Windows do usuário. Certificados, senhas, PINs, perfil do navegador, sessões, planilhas reais e relatórios fiscais não devem ser versionados.

## Estado da migração

O protótipo anterior foi analisado e o contrato Excel <-> automação foi identificado. A estratégia principal agora é **preservar o VBA e os botões existentes** e substituir apenas o processamento da Receita por um worker Python compatível com os arquivos que o Excel já produz.

A planilha real usada na análise continha dados empresariais e, por isso, não foi adicionada ao repositório.

Consulte também [`docs/migracao-prototipo.md`](docs/migracao-prototipo.md).

## O que foi implementado

- Python 3.11+ com Playwright assíncrono.
- Conexão ao Chrome já preparado pelo protótipo via CDP (`http://127.0.0.1:9225`).
- Login, certificado e desafios de segurança permanecem manuais.
- Leitura direta do `fila.json` criado pelo VBA.
- Somente CNPJs válidos entram no processamento automático da Receita; CPF e CAEPF ficam manuais.
- Compatibilidade com `progresso.json`, `progresso.txt`, `resultado.json` e `resultado.tsv`.
- Preservação dos resultados após cada empresa.
- Retomada de resultados concluídos quando o mesmo `fila.json` é executado novamente.
- Pausa por `pausar.flag` e interrupção pelo script já chamado pelo Excel.
- Intervalo mínimo de 40 segundos antes da próxima representação.
- Campo interno do CNPJ: `input[placeholder="Digite o CPF ou CNPJ"]`.
- Submit específico: `button[type="submit"].br-button.primary.block.margin-5`.
- Perfil `Procurador` delimitado ao mesmo formulário do CNPJ.
- Sequência crítica exatamente: clique em Procurador -> `Tab` -> 300 ms -> `Tab` -> 300 ms -> `Space`.
- Nenhum `focus()`, `evaluate()`, leitura do portal ou gravação de arquivo é inserido entre essas teclas.
- Confirmação da representação separada da ação de envio.
- Resultado aceito apenas quando o conteúdo principal exibe `Resultado da Análise`, o CNPJ solicitado e um marcador explícito `Com pendência`/`Sem pendência`.
- Falha de confirmação da representação interrompe o lote (fail-closed).
- `Sem procuração ativa` somente é usado quando existe mensagem explícita correspondente no portal.
- Download do relatório com clique normal do Playwright; não usa `force=True` como tentativa cega.
- Evidências e logs ficam somente na pasta local da execução.
- Fluxo FGTS continua delegado ao worker Node anterior nesta etapa.

## Estrutura principal

```text
src/receita_automacao/
    queue_worker.py        # worker compatível com a fila do Excel
    portal.py              # scaffold anterior de acesso direto
    ...
integracao_excel/automacao/
    iniciar-consulta.ps1   # usa Python para RECEITA e mantém Node para FGTS
    parar-consulta.ps1     # interrompe Python ou Node e preserva contadores
scripts/
    preparar-ambiente.ps1
    instalar-integracao-excel.ps1
tests/
    test_queue_worker.py
```

## 1. Preparar o ambiente Python

Na pasta local do repositório:

```powershell
Set-Location "C:\Users\Cezar.CONTALEX\Desktop\GitHub\Pendências Fiscais Receita"
PowerShell -ExecutionPolicy Bypass -File ".\scripts\preparar-ambiente.ps1"
```

O script:

- cria `.venv`;
- instala o projeto e dependências;
- registra `PENDENCIAS_RECEITA_REPO` para a integração Excel;
- não instala outro navegador, pois o worker conecta ao Chrome do protótipo via CDP.

## 2. Instalar a integração no protótipo Excel

**Não execute esta etapa com uma planilha diferente sem revisar o caminho.** O instalador não modifica células, fórmulas ou VBA. Ele altera apenas os scripts da pasta `Pendencias Fiscais\automacao` ao lado do workbook e cria backup antes.

Exemplo:

```powershell
Set-Location "C:\Users\Cezar.CONTALEX\Desktop\GitHub\Pendências Fiscais Receita"
PowerShell -ExecutionPolicy Bypass -File ".\scripts\instalar-integracao-excel.ps1" `
  -WorkbookPath "C:\CAMINHO\Controle_Folha_Cezar_Prototipo_Pendencias_v1.xlsm"
```

Durante a instalação:

- o `iniciar-consulta.ps1` anterior é preservado como `iniciar-consulta-node.ps1`;
- RECEITA passa a chamar o worker Python;
- FGTS continua chamando o script Node original;
- `parar-consulta.ps1` passa a reconhecer ambos os workers.

## 3. Primeiro teste controlado

Para não alterar lançamentos da planilha de trabalho, faça o primeiro teste em **uma cópia local do workbook**. O fluxo de importação do VBA grava o resultado da empresa consultada quando a execução termina.

1. Abra a cópia de teste da planilha.
2. Use o botão **Preparar navegador**.
3. Faça login com certificado manualmente.
4. Na aba de pendências, selecione **uma única empresa CNPJ**.
5. Acione a consulta da Receita e escolha **Empresas Selecionadas**.
6. Acompanhe a barra de progresso da própria planilha.
7. Se aparecer CAPTCHA/desafio de segurança, resolva manualmente no Chrome.
8. Se aparecer um diálogo adicional de confirmação de representação, confirme manualmente; o worker aguardará a conclusão e registrará essa etapa.

Não considere a integração validada antes de confirmar no teste real que:

- o CNPJ realmente mudou para a empresa solicitada;
- `Resultado da Análise` pertence ao mesmo CNPJ;
- o resultado `Com/Sem pendência` foi importado na linha correta;
- quando houver pendências, o relatório foi baixado e o caminho foi gravado.

## Diagnóstico local

Cada execução criada pela planilha contém, conforme aplicável:

```text
fila.json
progresso.json
progresso.txt
resultado.json
resultado.tsv
worker-python.stdout.log
worker-python.stderr.log
automacao-python.jsonl
evidencias\
relatorios\
```

Os diagnósticos distinguem pelo menos:

- login necessário;
- desafio de segurança;
- campo interno de CNPJ não encontrado;
- submit Representar ausente, múltiplo ou desabilitado;
- campo Procurador não localizado;
- opção Procurador não única;
- sequência Tab/Tab/Espaço enviada;
- confirmação adicional do portal;
- representação não confirmada;
- CNPJ divergente;
- resultado não carregado;
- ausência explícita de procuração;
- falha/instabilidade no download.

## Testes automáticos

```powershell
Set-Location "C:\Users\Cezar.CONTALEX\Desktop\GitHub\Pendências Fiscais Receita"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
```

Os testes do worker cobrem, sem acessar o portal:

- filtragem da fila para CNPJ válido;
- exigência do CNPJ solicitado no resultado;
- proibição de classificar erro genérico como ausência de procuração;
- compatibilidade do TSV com o VBA;
- ordem exata da sequência `Procurador -> Tab -> 300 ms -> Tab -> 300 ms -> Space`.

## O que significa "validado"

1. **Implementado:** código versionado no repositório.
2. **Testado automaticamente:** comportamento isolado exercitado sem portal autenticado.
3. **Validado no portal:** somente após execução local com o Chrome autenticado e confirmação da troca real do CNPJ.

Nesta etapa, os testes unitários podem validar a lógica isolada. A validação real do portal obrigatoriamente ocorrerá no Windows do usuário.
