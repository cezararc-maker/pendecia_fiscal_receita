# Primeiro teste controlado no Windows

Este procedimento valida a integração Excel -> PowerShell -> Python -> Playwright -> Portal da Receita com risco reduzido.

## Regra principal

O primeiro teste deve ser feito em uma **cópia da pasta do protótipo**, nunca diretamente na planilha de trabalho.

A cópia precisa manter a estrutura:

```text
PASTA_DO_TESTE\
  Controle_Folha_....xlsm
  Pendencias Fiscais\
    automacao\
```

## 1. Instalar a integração em modo de validação

Na pasta local do repositório:

```powershell
Set-Location "C:\Users\Cezar.CONTALEX\Desktop\GitHub\Pendências Fiscais Receita"

PowerShell -ExecutionPolicy Bypass -File ".\scripts\instalar-integracao-excel.ps1" `
  -WorkbookPath "C:\CAMINHO\DA\COPIA\Controle_Folha_Cezar_Prototipo_Pendencias_v1.xlsm" `
  -ValidationMode
```

O instalador:

- preserva a planilha;
- cria backup dos scripts existentes;
- mantém o worker Node original para FGTS;
- instala o worker Python para Receita;
- cria `modo-validacao-uma-empresa.flag` na pasta de automação.

Enquanto esse marcador existir, uma fila da Receita com quantidade diferente de **1 empresa** será bloqueada antes de iniciar o worker.

## 2. Executar somente uma empresa CNPJ

1. Abra a cópia da planilha.
2. Clique em **Preparar navegador**.
3. Faça login/certificado manualmente.
4. Confirme que o Portal da Receita abriu a área de pendências.
5. Na planilha, selecione exatamente **uma empresa com CNPJ**.
6. Inicie a consulta da Receita usando o escopo de empresas selecionadas.
7. Não marque uma segunda empresa nesta etapa.
8. Resolva manualmente qualquer CAPTCHA, confirmação adicional ou desafio de segurança.

Se a fila tiver zero ou mais de uma empresa, o modo de validação deve impedir a execução e registrar `ERRO_FATAL` no progresso.

## 3. Critérios de aprovação

O primeiro teste só é considerado aprovado se todos os itens abaixo forem confirmados:

- a representação mudou para o CNPJ solicitado;
- o CNPJ exibido em `Resultado da Análise` corresponde ao solicitado;
- o retorno `Com pendência` ou `Sem pendência` foi identificado corretamente;
- o resultado foi importado na linha correta do Excel;
- quando houver pendências, o relatório foi realmente baixado;
- o caminho do relatório foi gravado no resultado;
- nenhum segundo CNPJ foi processado;
- nenhuma falha genérica foi classificada como `Sem procuração ativa`.

## 4. Arquivos para diagnóstico

Na pasta da execução, preservar para análise local:

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

Não publicar esses arquivos no GitHub sem sanitização, pois podem conter dados empresariais.

## 5. Depois da validação

Somente depois do primeiro teste aprovado, remova o bloqueio de uma empresa:

```powershell
Set-Location "C:\Users\Cezar.CONTALEX\Desktop\GitHub\Pendências Fiscais Receita"

PowerShell -ExecutionPolicy Bypass -File ".\scripts\desativar-modo-validacao.ps1" `
  -WorkbookPath "C:\CAMINHO\DA\COPIA\Controle_Folha_Cezar_Prototipo_Pendencias_v1.xlsm"
```

A remoção do marcador apenas libera filas maiores; não altera a lógica de segurança de confirmação do CNPJ, o intervalo de 40 segundos ou a interrupção fail-closed.
