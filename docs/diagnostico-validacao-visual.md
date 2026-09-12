# Diagnóstico da validação visual do Portal da Receita

Objetivo: identificar em qual etapa da representação a validação visual passa a aparecer, sem tentar contornar ou automatizar o mecanismo de segurança do portal.

## Premissas

- usar a cópia de teste da planilha;
- usar sempre uma única empresa CNPJ por ensaio;
- preferencialmente usar a mesma empresa nos três ensaios;
- antes de cada ensaio, voltar manualmente ao perfil próprio/representação inicial para evitar que o portal informe que o representado já está ativo;
- usar o mesmo Chrome aberto por `Preparar navegador` e a mesma sessão autenticada;
- se a validação visual aparecer, resolvê-la manualmente;
- não alterar tempos, fingerprint, `navigator.webdriver`, eventos de mouse, cookies ou outros sinais com a finalidade de evitar a validação.

O modo diagnóstico força exatamente 1 CNPJ, mesmo que o modo de validação normal esteja configurado para 2 ou mais empresas.

## Ensaio A — Python só preenche o CNPJ

Ativar:

```powershell
PowerShell -ExecutionPolicy Bypass -File ".\scripts\ativar-diagnostico-receita.ps1" `
  -WorkbookPath "C:\CAMINHO\DA\COPIA\Controle_Folha_Cezar_Prototipo_Pendencias_v1.xlsm" `
  -Stage after-cnpj
```

Executar a consulta da Receita para uma única empresa.

O Python deve:

1. abrir a área de representação;
2. preencher o CNPJ;
3. parar.

A partir daí, o usuário deve manualmente:

1. abrir o campo de perfil;
2. escolher `Procurador`;
3. clicar em `Representar`;
4. resolver eventual validação visual.

Registrar se a validação apareceu.

## Ensaio B — Python seleciona Procurador, envio manual

Ativar:

```powershell
PowerShell -ExecutionPolicy Bypass -File ".\scripts\ativar-diagnostico-receita.ps1" `
  -WorkbookPath "C:\CAMINHO\DA\COPIA\Controle_Folha_Cezar_Prototipo_Pendencias_v1.xlsm" `
  -Stage after-procurador
```

O Python deve:

1. abrir a área de representação;
2. preencher o CNPJ;
3. abrir o seletor de perfil;
4. escolher `Procurador`;
5. parar antes de enviar.

O usuário deve clicar manualmente em `Representar` e resolver eventual validação visual.

Registrar se a validação apareceu.

## Ensaio C — fluxo automático completo

Ativar o modo `full`:

```powershell
PowerShell -ExecutionPolicy Bypass -File ".\scripts\ativar-diagnostico-receita.ps1" `
  -WorkbookPath "C:\CAMINHO\DA\COPIA\Controle_Folha_Cezar_Prototipo_Pendencias_v1.xlsm" `
  -Stage full
```

O modo `full` força uma única empresa, mas executa exatamente o fluxo automático normal: CNPJ -> Procurador -> envio da representação.

Registrar se a validação apareceu.

## Encerrar o diagnóstico

Depois dos três ensaios:

```powershell
PowerShell -ExecutionPolicy Bypass -File ".\scripts\desativar-diagnostico-receita.ps1" `
  -WorkbookPath "C:\CAMINHO\DA\COPIA\Controle_Folha_Cezar_Prototipo_Pendencias_v1.xlsm"
```

A integração volta ao modo de validação normal que já estiver configurado, por exemplo 2 empresas.

## Como interpretar

- **A sem validação; B sem validação; C com validação:** o gatilho está fortemente associado ao envio automatizado ou à sequência imediatamente ligada ao envio.
- **A sem validação; B com validação:** a seleção automatizada de `Procurador` ou os eventos anteriores ao envio passam a ser suspeitos.
- **A com validação:** apenas preencher/interagir automaticamente com a representação já é suficiente para acionar a validação naquela sessão.
- **Resultados inconsistentes entre repetições:** o portal provavelmente usa critérios adicionais de risco/frequência/sessão; repetir o ensaio antes de concluir.

Esses resultados indicam correlação no ambiente observado, não revelam os critérios internos do portal.

## Espera manual segura

Durante os modos `after-cnpj` e `after-procurador`, o worker aguarda até 5 minutos pelo `Resultado da Análise`. Se a tela `Confirme que você é uma pessoa` aparecer, ela é tratada como desafio de segurança manual: o worker aguarda e retoma depois que o usuário a conclui.
