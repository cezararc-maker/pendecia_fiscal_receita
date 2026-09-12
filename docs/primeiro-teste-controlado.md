# Primeiro teste controlado no Windows

Este procedimento valida a integração Excel -> PowerShell -> Python -> Playwright -> Portal da Receita com risco reduzido.

## Regra principal

Os testes devem ser feitos em uma **cópia da pasta do protótipo**, nunca diretamente na planilha de trabalho.

A cópia precisa manter a estrutura:

```text
PASTA_DO_TESTE\
  Controle_Folha_....xlsm
  Pendencias Fiscais\
    automacao\
```

## Fase 1 - uma empresa

A primeira fase validou o caminho estrutural até a representação:

1. preencher o CNPJ;
2. localizar o mesmo formulário do botão Representar;
3. abrir `Digite um perfil de representação`;
4. usar preferencialmente a seta `.ng-arrow-wrapper` do `ng-select`, com o placeholder como fallback;
5. localizar a opção `Procurador`;
6. executar imediatamente `Tab -> 300 ms -> Tab -> 300 ms -> Space` após clicar em Procurador.

### Comportamento esperado do botão Representar

No portal real, após preencher o CNPJ, o botão **Representar** permanece visível porém **desabilitado** enquanto nenhum perfil foi escolhido. Isso é esperado.

O worker não trata esse estado como erro. A habilitação acontece como consequência da seleção de `Procurador`; a confirmação de sucesso continua sendo feita somente depois, pelo CNPJ e pelo `Resultado da Análise` exibidos pelo portal.

## Fase 2 - exatamente duas empresas

A segunda fase serve exclusivamente para validar a troca entre representações. Reinstale a integração na mesma cópia com:

```powershell
Set-Location "C:\Users\Cezar.CONTALEX\Desktop\GitHub\Pendências Fiscais Receita"

PowerShell -ExecutionPolicy Bypass -File ".\scripts\instalar-integracao-excel.ps1" `
  -WorkbookPath "C:\CAMINHO\DA\COPIA\Controle_Folha_Cezar_Prototipo_Pendencias_v1.xlsm" `
  -ValidationMode `
  -ValidationCompanyCount 2
```

O marcador de validação passa a registrar `EMPRESAS=2`. Enquanto estiver ativo, qualquer fila diferente de exatamente **2 empresas CNPJ** será bloqueada antes de iniciar o worker.

### O que observar

1. selecione exatamente duas empresas CNPJ na cópia da planilha;
2. a primeira representação deve seguir o fluxo já validado;
3. caso o portal mostre validação por imagens, CAPTCHA ou outro desafio de segurança, resolva-o **manualmente**;
4. o worker deve aguardar o desafio desaparecer e continuar sem tentar resolvê-lo automaticamente;
5. depois de concluir a primeira empresa, o worker deve respeitar o intervalo mínimo de 40 segundos antes da próxima representação;
6. em seguida deve reabrir a área Representar, preencher o segundo CNPJ, abrir o perfil pela seta/placeholder, selecionar Procurador e executar a mesma sequência crítica;
7. o segundo resultado só pode ser aceito se `Resultado da Análise` exibir o segundo CNPJ solicitado e marcador explícito `Com pendência` ou `Sem pendência`.

## Desafios de segurança

A tela de seleção de imagens exibida pelo portal é tratada como **gate manual**. O projeto não tenta clicar nas imagens, automatizar a resposta nem contornar o mecanismo. O worker apenas detecta a tela, muda o progresso para aguardando validação e retoma quando o desafio deixa de estar visível.

O padrão observado no portal inclui texto semelhante a `Selecione tudo mais silencioso que o item mostrado` e foi adicionado à detecção de desafios.

## Critérios de aprovação da troca entre empresas

O teste de duas empresas só é aprovado quando:

- a primeira empresa é representada corretamente;
- qualquer desafio de segurança é resolvido manualmente e a execução continua;
- a primeira empresa tem resultado confirmado pelo próprio CNPJ exibido;
- há pelo menos 40 segundos entre a primeira ação de representação e a tentativa da segunda;
- a segunda empresa recebe exatamente o mesmo fluxo de representação já estabilizado;
- o CNPJ exibido no segundo `Resultado da Análise` corresponde ao segundo CNPJ da fila;
- o retorno `Com pendência` ou `Sem pendência` é associado à linha correta;
- quando houver pendências, o relatório é realmente baixado e o caminho gravado;
- nenhuma falha genérica é classificada como `Sem procuração ativa`.

## Arquivos para diagnóstico

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

## Depois da validação

Somente depois do teste de duas empresas aprovado, remova o bloqueio de validação:

```powershell
Set-Location "C:\Users\Cezar.CONTALEX\Desktop\GitHub\Pendências Fiscais Receita"

PowerShell -ExecutionPolicy Bypass -File ".\scripts\desativar-modo-validacao.ps1" `
  -WorkbookPath "C:\CAMINHO\DA\COPIA\Controle_Folha_Cezar_Prototipo_Pendencias_v1.xlsm"
```

A remoção do marcador libera filas maiores; não altera a lógica de confirmação do CNPJ, o intervalo de 40 segundos nem a interrupção fail-closed.
