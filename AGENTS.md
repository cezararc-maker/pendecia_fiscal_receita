# AGENTS.md

## Project safety rules

1. The GitHub repository is the source of truth for code, tests, examples and documentation.
2. Never commit certificates, passwords, PINs, cookies, browser profiles, storage-state files, real Excel workbooks, fiscal reports or screenshots from authenticated sessions.
3. GitHub Actions may run unit/static tests only. It must never authenticate to Receita Federal or execute fiscal queries.
4. The real `.xlsm` is handled only on the user's Windows machine. Use Excel COM (`pywin32`) for updates so macros, buttons, formulas and workbook features are preserved.
5. Only rows explicitly typed as `CNPJ` are eligible for automatic processing. CPF and CAEPF remain manual.
6. Portal automation is fail-closed: submitting the representation form is not success. Confirm the requested CNPJ in cadastral/result data before accepting any fiscal result.
7. Never classify navigation errors, missing companies or generic failures as `sem procuração ativa`. That status requires an explicit portal message.
8. The Procurador submission sequence is intentional. After clicking the `Procurador` option, execute immediately `Tab`, wait 300 ms, `Tab`, wait 300 ms, `Space`. Do not focus elements, evaluate JavaScript, write files or perform diagnostics between those actions.
9. Do not combine the keyboard submission sequence with a second blind click on the submit button.
10. Keep the 40-second representation interval before the next company, never between selecting Procurador and submitting.
11. Runtime logs/evidence are local and ignored by git. They may contain business information and must not be uploaded to issues/PRs without sanitization.
