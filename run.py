"""
Script auxiliar de execução — Desenvolvimento Local.

Sobe os containers Docker (PostgreSQL), executa as migrações
do banco de dados (Alembic) e inicia o servidor FastAPI (Uvicorn).
Funciona de forma idêntica no Windows, macOS e Linux.
"""

import shutil
import subprocess
import sys
import time


def executar_comando_python(comando):
    """Executa um módulo Python usando o interpretador do ambiente virtual ativo."""
    subprocess.run(
        [sys.executable, "-m"] + comando,
        check=True,
    )


def executar_comando_shell(comando):
    """Executa um comando do sistema operacional (ex: docker)."""
    subprocess.run(
        comando,
        check=True,
    )


def encontrar_docker_compose():
    """Detecta qual comando Docker Compose está disponível no sistema."""
    # Docker Compose V2 (plugin): docker compose
    if shutil.which("docker"):
        resultado = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            check=False,
        )
        if resultado.returncode == 0:
            return ["docker", "compose"]

    # Docker Compose V1 (standalone): docker-compose
    if shutil.which("docker-compose"):
        return ["docker-compose"]

    return None


def main():
    print("─── [Weeklies Backend] Iniciando ambiente de desenvolvimento ───")

    # 1. Subir os containers Docker (PostgreSQL, pgAdmin e Redis)
    print("\n[1/3] Subindo containers Docker (PostgreSQL, Redis)...")
    docker_compose = encontrar_docker_compose()

    if docker_compose is None:
        print("❌ Docker Compose não encontrado. Instale o Docker antes de continuar.")
        sys.exit(1)

    try:
        executar_comando_shell(docker_compose + ["up", "-d"])
        print("✅ Containers Docker iniciados com sucesso.")
    except subprocess.CalledProcessError:
        print("❌ Erro ao subir os containers Docker.")
        sys.exit(1)

    # Aguardar o banco de dados ficar disponível
    print("⏳ Aguardando o banco de dados ficar pronto...")
    time.sleep(3)

    # 2. Executar migrações pendentes
    print("\n[2/3] Aplicando migrações do banco de dados (Alembic)...")
    try:
        executar_comando_python(["alembic", "upgrade", "head"])
        print("✅ Banco de dados atualizado com sucesso.")
    except subprocess.CalledProcessError:
        print("❌ Erro ao aplicar migrações. Verifique se o container do banco está saudável.")
        sys.exit(1)

    # 3. Iniciar o servidor Uvicorn
    print("\n[3/3] Iniciando o servidor Uvicorn...")
    print("📄 Swagger UI: http://localhost:8000/docs")
    print("❤️  Health check: http://localhost:8000/api/health\n")
    try:
        executar_comando_python([
            "uvicorn",
            "app.main:app",
            "--reload",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ])
    except KeyboardInterrupt:
        print("\n👋 Servidor finalizado pelo usuário.")
    except subprocess.CalledProcessError:
        # Uvicorn retorna código não-zero ao receber Ctrl+C (SIGINT).
        # Isso é comportamento normal de encerramento, não um erro real.
        print("\n👋 Servidor finalizado.")
    finally:
        print("\n🛑 Parando containers Docker (PostgreSQL, Redis)...")
        try:
            executar_comando_shell(docker_compose + ["down"])
            print("✅ Containers parados com sucesso.")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Não foi possível parar os containers automaticamente: {e}")


if __name__ == "__main__":
    main()
