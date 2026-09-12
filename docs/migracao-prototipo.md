# Migração do protótipo JavaScript para Python

## Insumos analisados

Foram analisados localmente, sem publicar dados reais:

- `worker.mjs` implantado;
- código-fonte do protótipo (PowerShell, VBA, UserForm e automação);
- cópia integral da planilha `.xlsm` apenas para conferir estrutura e integração.

A planilha recebida continha dados reais e **não foi adicionada ao GitHub**.

## Contrato existente preservado

A migração da Receita não reescreve a planilha. O Excel continua responsável por:

1. escolher o escopo da consulta;
2. criar `fila.json`;
3. mostrar progresso lendo `progresso.txt`;
4. pausar por `pausar.flag`;
5. interromper pelo script `parar-consulta.ps1`;
6. importar `resultado.tsv` para a aba `Pendencias Fiscais`.

O worker Python mantém os mesmos arquivos de integração.

### Estrutura confirmada da aba `Pendencias Fiscais`

Cabeçalho na linha 5, dados a partir da linha 6:

| Coluna | Cabeçalho |
|---|---|
| A | Selecionar |
| B | Codigo |
| C | Nome reduzido |
| D | Tipo de inscricao |
| E | CNPJ |
| F | CPF |
| G | CAEPF |
| H | CEI |
| I | Situacao |
| J | Regime |
| K | Ativa |
| L | Status Receita |
| M | Resultado Receita |
| N | Relatorio Receita |
| O | Data e Hora Receita |
| P | Status FGTS |
| Q | Qtde competencias abertas |
| R | Competencias abertas |
| S | Data e Hora FGTS |
| T | Observacoes |

### Fila criada pelo VBA

O worker lê os campos já produzidos pelo protótipo:

- `tipo`;
- `cdpUrl`;
- `progressPath`;
- `progressTextPath`;
- `resultPath`;
- `resultTsvPath`;
- `pausePath`;
- `outputDirectory`;
- `empresas[]` com `codigo`, `nome`, `tipoInscricao`, `cnpj`, `cpf`, `caepf`, `identificador` e `tipoIdentificador`.

Nesta etapa o worker Python aceita somente `RECEITA` e filtra a execução automática para CNPJs válidos. CPF e CAEPF permanecem fora do processamento automático.

### Resultado TSV preservado

A ordem das colunas continua:

`codigo`, `nome`, `dataHora`, `status`, `resultado`, `relatorio`, `quantidade`, `competencias`, `detalhes`.

Isso permite que o VBA existente continue importando os resultados para L:O sem mudança estrutural na planilha.

## Migração do navegador

O protótipo já abre um Chrome exclusivo com depuração remota na porta 9225. Essa estratégia foi preservada porque:

- o login com certificado continua manual;
- a sessão autenticada não é exportada nem versionada;
- o Python usa `chromium.connect_over_cdp(...)` e não controla mouse/teclado do Windows;
- o botão existente `Preparar navegador` pode continuar sendo usado.

## Fluxo da Receita migrado

1. localizar a página da Receita no Chrome preparado;
2. confirmar que não houve redirecionamento para login;
3. aguardar desafios de segurança resolvidos manualmente;
4. respeitar 40 segundos antes da próxima representação;
5. abrir a barra lateral por `#avatar-dropdown-trigger`;
6. usar o input interno `input[placeholder="Digite o CPF ou CNPJ"]`;
7. localizar o submit único `button[type="submit"].br-button.primary.block.margin-5`;
8. delimitar o mesmo formulário do CNPJ;
9. selecionar o input interno do `ng-select` e a opção `Procurador`;
10. executar sem operações intermediárias: `Tab` -> 300 ms -> `Tab` -> 300 ms -> `Space`;
11. caso o portal exiba um diálogo adicional distinto, aguardar confirmação manual e registrá-la como etapa própria;
12. confirmar o CNPJ no conteúdo principal associado a `Resultado da Análise` e exigir marcador explícito `Com pendência` ou `Sem pendência`;
13. interromper o lote se a representação não puder ser confirmada com segurança;
14. baixar relatório somente quando houver pendências;
15. salvar resultado após cada empresa.

## FGTS

A migração inicial não substitui o worker do FGTS. O wrapper PowerShell delega filas `FGTS` ao `iniciar-consulta-node.ps1` original, preservado durante a instalação.

## Dados que não são versionados

- planilhas reais;
- certificados e PINs;
- perfil de navegador;
- cookies/sessões;
- `fila.json` e execuções reais;
- relatórios fiscais;
- screenshots/evidências autenticadas;
- logs de execução com contexto empresarial.
