import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional, Tuple

from cue_chd_converter.models import CueGame


LogCallback = Callable[[str], None]


class ChdConverter:
    def __init__(self, chdman_path: Path):
        self.chdman_path = chdman_path

    def convert(
        self,
        game: CueGame,
        output_path: Path,
        overwrite: bool = False,
        on_log: Optional[LogCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Tuple[bool, str]:
        if not self.chdman_path.exists():
            detail = _build_precheck_failure_details(
                title="Falha de pré-validação",
                game=game,
                output_path=output_path,
                chdman_path=self.chdman_path,
                reason="chdman não encontrado",
                hint="Coloque chdman.exe em tools\\mame\\chdman.exe",
            )
            if on_log:
                on_log(detail)
            return False, "Falha de pré-validação (chdman ausente)"

        if output_path.exists() and not overwrite:
            detail = _build_precheck_failure_details(
                title="Falha de pré-validação",
                game=game,
                output_path=output_path,
                chdman_path=self.chdman_path,
                reason="arquivo de saída já existe",
                hint="Ative a opção de sobrescrever .chd existente",
            )
            if on_log:
                on_log(detail)
            return False, "Falha de pré-validação (arquivo de saída já existe)"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        command = [
            str(self.chdman_path),
            "createcd",
            "-i",
            str(game.cue_path),
            "-o",
            str(output_path),
        ]

        if overwrite:
            command.append("-f")

        if on_log:
            on_log("Comando: {0}".format(" ".join(_quote(arg) for arg in command)))

        process: Optional[subprocess.Popen[str]] = None
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            detail = _build_precheck_failure_details(
                title="Falha ao iniciar chdman",
                game=game,
                output_path=output_path,
                chdman_path=self.chdman_path,
                reason=str(exc),
                hint="Verifique permissões de execução e DLLs do MAME",
            )
            if on_log:
                on_log(detail)
            return False, "Falha ao iniciar chdman"

        stdout, stderr, canceled = _wait_process_with_cancel(process, cancel_event)
        combined_output = "\n".join(part for part in [stdout, stderr] if part).strip()
        if combined_output and on_log:
            on_log(combined_output)

        if canceled:
            return False, "Conversão cancelada pelo usuário"

        if process.returncode != 0:
            detail = _build_runtime_failure_details(
                game=game,
                output_path=output_path,
                chdman_path=self.chdman_path,
                command=command,
                return_code=process.returncode,
                stdout=stdout,
                stderr=stderr,
            )
            if on_log:
                on_log(detail)
            return False, "Falha na conversão (detalhes no log)"

        return True, "Conversão concluída"


def _quote(arg: str) -> str:
    if " " in arg or '"' in arg:
        return '"{0}"'.format(arg.replace('"', '\\"'))
    return arg


def _wait_process_with_cancel(
    process: subprocess.Popen[str], cancel_event: Optional[threading.Event]
) -> Tuple[str, str, bool]:
    while True:
        if cancel_event and cancel_event.is_set():
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            return stdout, stderr, True

        try:
            stdout, stderr = process.communicate(timeout=0.2)
            return stdout, stderr, False
        except subprocess.TimeoutExpired:
            continue


def _build_precheck_failure_details(
    title: str,
    game: CueGame,
    output_path: Path,
    chdman_path: Path,
    reason: str,
    hint: str,
) -> str:
    lines = [
        "[ERRO DETALHADO] {0}".format(title),
        "Jogo: {0}".format(game.display_name),
        "Origem: {0}".format(game.cue_path),
        "Saída: {0}".format(output_path),
        "chdman: {0}".format(chdman_path),
        "Causa: {0}".format(reason),
        "Sugestão: {0}".format(hint),
    ]
    return "\n".join(lines)


def _build_runtime_failure_details(
    game: CueGame,
    output_path: Path,
    chdman_path: Path,
    command: list[str],
    return_code: int,
    stdout: str,
    stderr: str,
) -> str:
    diagnosis, hint = _infer_failure_cause(stdout=stdout, stderr=stderr)
    lines = [
        "[ERRO DETALHADO] Falha na conversão via chdman",
        "Jogo: {0}".format(game.display_name),
        "Origem: {0}".format(game.cue_path),
        "Saída: {0}".format(output_path),
        "chdman: {0}".format(chdman_path),
        "Código de retorno: {0}".format(return_code),
        "Diagnóstico provável: {0}".format(diagnosis),
        "Sugestão: {0}".format(hint),
        "Comando completo: {0}".format(" ".join(_quote(arg) for arg in command)),
    ]

    stderr_clean = _clean_output(stderr)
    stdout_clean = _clean_output(stdout)

    if stderr_clean:
        lines.append("STDERR:")
        lines.append(stderr_clean)
    if stdout_clean:
        lines.append("STDOUT:")
        lines.append(stdout_clean)

    return "\n".join(lines)


def _infer_failure_cause(stdout: str, stderr: str) -> Tuple[str, str]:
    merged = "{0}\n{1}".format(stdout, stderr).lower()

    if "no such file" in merged or "cannot find" in merged or "unable to open" in merged:
        return "arquivo de entrada ausente ou caminho inválido", "Verifique se o .cue e arquivos referenciados existem"
    if "permission denied" in merged or "access is denied" in merged:
        return "permissão negada ao ler/escrever arquivos", "Execute em pasta com permissão de escrita e sem bloqueio"
    if "already exists" in merged or "file exists" in merged:
        return "arquivo de saída já existe", "Ative sobrescrita ou remova o .chd existente"
    if "unsupported" in merged or "not supported" in merged:
        return "formato não suportado pelo chdman", "Valide o conteúdo do .cue e trilhas referenciadas"
    if "out of memory" in merged:
        return "memória insuficiente durante a conversão", "Feche outros programas e tente novamente"
    if "error parsing" in merged or "parse error" in merged:
        return "arquivo .cue malformado", "Corrija o .cue ou use outro dump"
    if "crc" in merged:
        return "dados de entrada corrompidos", "Reextraia os arquivos ou obtenha outro dump"
    if "dll" in merged and "not found" in merged:
        return "dependências do chdman ausentes", "Copie DLLs do MAME junto ao chdman.exe"

    return "falha não categorizada retornada pelo chdman", "Consulte STDERR/STDOUT acima para identificar a causa"


def _clean_output(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""

    max_chars = 6000
    if len(cleaned) > max_chars:
        return "{0}\n...[saída truncada para {1} caracteres]...".format(cleaned[:max_chars], max_chars)
    return cleaned
