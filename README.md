# PSX CHD Converter

Aplicativo desktop para Windows que converte jogos de PlayStation em formato `.cue` para `.chd` usando `chdman.exe createcd` (MAME).

## Inspiração

Este projeto nasceu de uma necessidade real: compactar jogos de PS1 para uso em emuladores (incluindo o RetroPie), reduzindo o espaço ocupado em cartões de memória com capacidade limitada.  
Além da economia de armazenamento com o formato `.chd`, a proposta foi simplificar uma tarefa repetitiva com conversão em lote, permitindo processar várias ROMs de forma mais automática, rápida e organizada.

## O que já está implementado

- Executável portátil (sem instalador) via PyInstaller (`one-dir`).
- Organização do `chdman` em pasta separada: `tools/mame`.
- Seleção de:
  - pasta de ROMs
  - arquivo `.cue` único
- Varredura de ROMs compatíveis:
  - lista `.cue` válidos e compactados suportados
  - mostra visualmente os ignorados/incompatíveis com motivo
- Conversão:
  - ROM individual (selecionando 1 item)
  - múltiplas ROMs selecionadas
  - lote completo (todos listados)
- Extração automática de compactados antes da conversão:
  - `.zip`, `.7z`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, `.tar.xz`, `.txz`
  - `.rar` detectado e exibido como não suportado para extração automática
- Cancelamento de conversão em andamento (incluindo fila).
- Progresso de conversão:
  - atual/total considerando etapas de extração + conversão
  - status por jogo (`Pronto`, `Na fila`, `Convertendo`, `Convertido`, `Falhou`, `Cancelado`)
  - log detalhado do `chdman`, incluindo diagnóstico provável da causa em caso de falha
  - botão `Abrir log` para visualizar o log em janela separada (útil em telas pequenas)
  - alerta/modal ao finalizar (com som padrão do Windows)
- Destino configurável:
  - mesma pasta da ROM (padrão)
  - pasta de saída customizada
- Opção de sobrescrever `.chd` existente.
- Persistência de configurações:
  - última origem usada
  - destino padrão
  - sobrescrita
  - varredura recursiva
  - tamanho/posição da janela

## Estrutura do projeto

```
.
├─ src/
│  ├─ main.py
│  └─ cue_chd_converter/
│     ├─ cue_parser.py
│     ├─ scanner.py
│     ├─ converter.py
│     ├─ paths.py
│     ├─ models.py
│     └─ ui.py
├─ scripts/
│  ├─ run-dev.ps1
│  ├─ build.ps1
│  ├─ fetch-mame.ps1
│  └─ fetch-7zip.ps1
└─ tools/
   ├─ mame/
   │  └─ README.txt
   └─ 7zip/
      └─ README.txt
```

## Como usar em desenvolvimento

1. Coloque `chdman.exe` em `tools/mame/chdman.exe`.
2. Rode:

```powershell
python src/main.py
```

Para suporte a `.7z` em ambiente de desenvolvimento:

```powershell
python -m pip install py7zr
```

Alternativa sem `py7zr`: coloque `7z.exe` em `tools/7zip/7z.exe` (ou tenha `7z` no `PATH` do sistema).

## Como gerar executável portátil

1. Garanta que `chdman.exe` está em `tools/mame/chdman.exe`, ou use download automático.
2. Execute:

```powershell
.\scripts\build.ps1
```

3. A distribuição final ficará em `dist/CueChdConverter/`.

### Build com download automático do MAME (release oficial)

Baixa automaticamente o pacote oficial mais recente listado em `https://www.mamedev.org/release.html`, extrai `chdman.exe` (e DLLs necessárias) para `tools/mame`, também baixa `7zr.exe` oficial para `tools/7zip`, e depois executa o build:

```powershell
.\scripts\build.ps1 -FetchMame
```

Para forçar atualização mesmo já existindo `tools/mame/chdman.exe`:

```powershell
.\scripts\build.ps1 -FetchMame -ForceMameRefresh
```

Também é possível baixar sem build:

```powershell
.\scripts\fetch-mame.ps1 -OutputDir tools/mame
```

Baixar apenas o 7-Zip sem build:

```powershell
.\scripts\fetch-7zip.ps1 -OutputDir tools/7zip
```

Para fixar uma versão específica com URL direta:

```powershell
.\scripts\fetch-mame.ps1 -PackageUrl https://github.com/mamedev/mame/releases/download/mame0286/mame0286b_x64.exe
```

Para forçar atualização do 7-Zip no build:

```powershell
.\scripts\build.ps1 -FetchMame -Force7ZipRefresh
```

## Compatibilidade Windows

- Interface nativa com `tkinter/ttk` (tema automático conforme Windows).
- Para **Win10/Win11**: build normal com Python atual.
- Para **Win7**: gere o build com **Python 3.8.x (64-bit)**, que é a linha com melhor compatibilidade legada para esse cenário.

## Observações

- O app valida arquivos referenciados dentro do `.cue` antes de listar como compatível.
- Arquivos não `.cue` ou `.cue` inválidos não entram na lista de conversão.
- Configurações ficam em `%APPDATA%\CueChdConverter\settings.json`.
- Compactados suportados aparecem em `ROMs compatíveis` e podem ser convertidos por seleção ou em lote.

## Créditos

- Desenvolvedor: **Felipe Stroff**
- Contato: **stroff.felipe@gmail.com** (dúvidas, sugestões e contato)
- GitHub: **https://github.com/felipestroff**

## Licença

Este projeto é distribuído sob licença de uso **não comercial**. O uso comercial e a comercialização do código são proibidos sem autorização prévia do autor. Consulte o arquivo [LICENSE](LICENSE).
