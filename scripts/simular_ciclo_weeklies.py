"""Script utilitário para simulação do ciclo de Weeklies e virada de tempo.

Permite simular manualmente os jobs do APScheduler:
1. Sexta 00:00 - Criação de weeklies em lote e rollover de tasks pendentes.
2. Terça 01:00 - Verificação de ausências (emissão de advertências) e auditoria de tasks vencidas.
3. Consulta de status de weeklies e advertências por setor e usuário.

Uso:
    python scripts/simular_ciclo_weeklies.py status
    python scripts/simular_ciclo_weeklies.py abrir-semana [--data YYYY-MM-DD]
    python scripts/simular_ciclo_weeklies.py fechar-semana [--data YYYY-MM-DD]
    python scripts/simular_ciclo_weeklies.py reset-execucao [--data YYYY-MM-DD]
    python scripts/simular_ciclo_weeklies.py avancar-ciclo
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone

# Adiciona o diretório raiz ao path para importar a aplicação
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.sector import Sector
from app.models.task import Task
from app.models.user import User
from app.models.weekly import Weekly
from app.models.weekly_scheduler_execution import WeeklySchedulerExecution
from app.models.weekly_task import WeeklyTask
from app.models.weekly_warning import WeeklyWarning
from app.weeklies.scheduler import (
    executar_criacao_weeklies_lote,
    executar_verificacao_ausencias,
)
from app.weeklies.timezone_utils import obter_semana_referencia


def parse_date(date_str: str | None) -> date:
    if date_str:
        try:
            return date.fromisoformat(date_str)
        except ValueError:
            print(f"❌ Formato de data inválido: {date_str}. Use AAAA-MM-DD (ex: 2026-10-26).")
            sys.exit(1)
    return obter_semana_referencia()


def cmd_status(db, args):
    """Exibe o panorama atual das weeklies, advertências e tarefas."""
    print("\n" + "=" * 60)
    print("📊 PANORAMA ATUAL DO MÓDULO DE WEEKLIES")
    print("=" * 60)

    semana = parse_date(args.data) if hasattr(args, "data") and args.data else obter_semana_referencia()
    print(f"🗓️ Semana de Referência consultada: {semana} (Segunda-feira)")

    # 1. Execuções registradas
    execucoes = (
        db.query(WeeklySchedulerExecution)
        .filter(WeeklySchedulerExecution.semana_referencia == semana)
        .all()
    )
    print("\n⚙️ Jobs executados para esta semana:")
    if execucoes:
        for ex in execucoes:
            print(f"  • [{ex.tipo}] em {ex.executado_em.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    else:
        print("  (Nenhum job do scheduler registrado para esta semana ainda)")

    # 2. Weeklies da semana
    weeklies = (
        db.query(Weekly)
        .filter(Weekly.semana_referencia == semana)
        .all()
    )
    print(f"\n📝 Weeklies da semana ({len(weeklies)} encontradas):")
    if weeklies:
        for w in weeklies:
            u = db.query(User).filter(User.id == w.usuario_id).first()
            s = db.query(Sector).filter(Sector.id == w.setor_id).first()
            tasks_count = db.query(WeeklyTask).filter(WeeklyTask.weekly_id == w.id).count()
            nome_usuario = u.nome_completo if u else str(w.usuario_id)
            nome_setor = s.nome if s else str(w.setor_id)
            print(f"  • Membro: {nome_usuario:25} | Setor: {nome_setor:15} | Status: {w.status:10} | Tasks: {tasks_count}")
    else:
        print("  (Nenhuma weekly gerada para esta semana)")

    # 3. Advertências da semana
    warnings = (
        db.query(WeeklyWarning)
        .filter(WeeklyWarning.semana_referencia == semana)
        .all()
    )
    print(f"\n⚠️ Advertências geradas para esta semana ({len(warnings)}):")
    if warnings:
        for adv in warnings:
            u = db.query(User).filter(User.id == adv.usuario_id).first()
            s = db.query(Sector).filter(Sector.id == adv.setor_id).first()
            nome_usuario = u.nome_completo if u else str(adv.usuario_id)
            nome_setor = s.nome if s else str(adv.setor_id)
            print(f"  • Membro: {nome_usuario:25} | Setor: {nome_setor:15} | Tipo: {adv.tipo:15} | Motivo: {adv.justificativa}")
    else:
        print("  (Nenhuma advertência para esta semana)")

    # 4. Tasks pendentes e em auditoria
    tasks = db.query(Task).filter(Task.status.in_(["PENDENTE", "EM_AUDITORIA"])).all()
    print(f"\n📌 Tarefas ativas no sistema ({len(tasks)} PENDENTES ou EM_AUDITORIA):")
    for t in tasks[:10]:
        u = db.query(User).filter(User.id == t.usuario_id).first()
        nome_usuario = u.nome_completo if u else "Desconhecido"
        prazo = str(t.prazo_conclusao) if t.prazo_conclusao else "Sem prazo"
        print(f"  • [{t.status:12}] '{t.titulo:30}' | Dono: {nome_usuario:20} | Prazo: {prazo}")
    if len(tasks) > 10:
        print(f"  ... e mais {len(tasks) - 10} tarefas.")
    print("=" * 60 + "\n")


def cmd_abrir_semana(db, args):
    """Simula o job de Sexta 00:00: cria weeklies e executa rollover de tarefas."""
    semana = parse_date(args.data)
    if semana.weekday() != 0:
        print(f"⚠️ Aviso: a data informada ({semana}) não é uma segunda-feira. A semana de referência é sempre uma segunda-feira!")
        ajustada = semana + timedelta(days=(7 - semana.weekday()) % 7)
        if semana.weekday() > 0:
            ajustada = semana - timedelta(days=semana.weekday())
        print(f"➡️ Ajustando para a segunda-feira correspondente: {ajustada}")
        semana = ajustada

    print(f"\n🚀 [SIMULAÇÃO DE SEXTA 00:00] Iniciando criação em lote para a semana de referência: {semana}")
    try:
        resultado = executar_criacao_weeklies_lote(db, semana_referencia=semana)
        print("✅ Sucesso:")
        print(f"   • Total de membros elegíveis : {resultado['total_membros']}")
        print(f"   • Weeklies criadas (RASCUNHO): {resultado['criadas']}")
        print(f"   • Weeklies já existentes     : {resultado['ignoradas']}")
        print(f"   • Erros                      : {resultado['erros']}")
        print(f"   • Expiradas do ciclo anterior: {resultado['expiracao'].get('total_expiradas', 0)}")
    except Exception as e:  # noqa: BLE001
        print(f"❌ Erro ao executar criação de weeklies: {e}")
        import traceback
        traceback.print_exc()


def cmd_fechar_semana(db, args):
    """Simula o job de Terça 01:00: verifica ausências, gera advertências e audita tasks."""
    semana = parse_date(args.data)
    if semana.weekday() != 0:
        semana = semana - timedelta(days=semana.weekday())

    print(f"\n🔍 [SIMULAÇÃO DE TERÇA 01:00] Verificando ausências e auditoria para a semana: {semana}")
    try:
        resultado = executar_verificacao_ausencias(db, semana_referencia=semana)
        print("✅ Processamento concluído com sucesso:")
        print(f"   • Advertências geradas       : {resultado.get('total_advertencias_geradas', 0)}")
        for adv in resultado.get("advertencias", []):
            print(f"     -> Membro {adv.get('usuario_id')}: {adv.get('tipo')} no setor {adv.get('setor_id')}")
        auditoria = resultado.get("auditoria", {})
        print(f"   • Tasks auditadas            : {auditoria.get('total_auditadas', 0)}")
        print(f"   • Tasks movidas para auditoria: {auditoria.get('total_escaladas', 0)}")
    except Exception as e:  # noqa: BLE001
        print(f"❌ Erro ao executar verificação de ausências: {e}")
        import traceback
        traceback.print_exc()


def cmd_reset_execucao(db, args):
    """Remove o registro de execução de job para permitir re-teste da mesma semana."""
    semana = parse_date(args.data)
    deletados = (
        db.query(WeeklySchedulerExecution)
        .filter(WeeklySchedulerExecution.semana_referencia == semana)
        .delete()
    )
    db.commit()
    print(f"🧹 Registros de execução limpos para a semana {semana} ({deletados} registros removidos).")
    print("Agora você pode rodar 'abrir-semana' ou 'fechar-semana' novamente para essa data.")


def cmd_avancar_ciclo(db, args):
    """Simula a passagem de 1 semana para o navegador sem mudar o relógio do sistema.

    1. Desloca todas as weeklies, advertências e execuções existentes 7 dias para trás.
    2. Consolida as weeklies que estavam na semana atual (agora semana_atual - 7d)
       como APROVADA e marca as tasks concluídas como CONCLUIDA (mantendo as demais PENDENTE).
    3. Executa a criação em lote para a semana atual do relógio, herdando as pendentes.
    """
    semana_atual = obter_semana_referencia()
    semana_anterior = semana_atual - timedelta(days=7)

    print("\n⏩ [AVANÇAR CICLO] Simulando virada de semana no banco...")
    print(f"   • Semana fechada (será movida para): {semana_anterior}")
    print(f"   • Nova semana aberta (vigente)     : {semana_atual}")

    try:
        # 1. Desloca registros do mais antigo para o mais recente para evitar conflito de unique constraint
        for w in db.query(Weekly).order_by(Weekly.semana_referencia.asc()).all():
            w.semana_referencia = w.semana_referencia - timedelta(days=7)
            db.flush()

        for adv in db.query(WeeklyWarning).order_by(WeeklyWarning.semana_referencia.asc()).all():
            adv.semana_referencia = adv.semana_referencia - timedelta(days=7)
            db.flush()

        for ex in (
            db.query(WeeklySchedulerExecution)
            .order_by(WeeklySchedulerExecution.semana_referencia.asc())
            .all()
        ):
            ex.semana_referencia = ex.semana_referencia - timedelta(days=7)
            db.flush()

        # 2. Consolida as weeklies que acabaram de sair da semana atual (agora em semana_anterior)
        weeklies_fechadas = (
            db.query(Weekly)
            .filter(Weekly.semana_referencia == semana_anterior)
            .all()
        )
        tasks_concluidas = 0
        for w in weeklies_fechadas:
            if w.status != "EXPIRADA":
                w.status = "APROVADA"
                w.avaliada_em = w.avaliada_em or datetime.now(timezone.utc)
            for wt in w.weekly_tasks:
                if wt.task:
                    if not wt.snapshot_titulo:
                        wt.snapshot_titulo = wt.task.titulo
                        wt.snapshot_descricao = wt.task.descricao
                        wt.snapshot_prazo_conclusao = wt.task.prazo_conclusao
                    if wt.concluida and wt.task.status == "PENDENTE":
                        wt.task.status = "CONCLUIDA"
                        tasks_concluidas += 1

        db.commit()

        # 3. Gera novas weeklies para a semana atual com rollover das tasks ainda PENDENTES
        resultado = executar_criacao_weeklies_lote(db, semana_referencia=semana_atual)

        print("✅ Ciclo avançado com sucesso!")
        print(f"   • Weeklies anteriores consolidadas : {len(weeklies_fechadas)}")
        print(f"   • Tasks marcadas como CONCLUIDA    : {tasks_concluidas}")
        print(f"   • Novas weeklies em RASCUNHO       : {resultado['criadas']}")
        print("💡 Recarregue a página no navegador para ver as tarefas herdadas!")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"❌ Erro ao avançar ciclo: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="Simulador do Ciclo de Weeklies (Learning Lab UFC)")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    # Subcomando status
    p_status = subparsers.add_parser("status", help="Exibe status das weeklies, advertências e tasks")
    p_status.add_argument("--data", help="Semana de referência (AAAA-MM-DD)")

    # Subcomando abrir-semana (Sexta 00h)
    p_abrir = subparsers.add_parser("abrir-semana", help="Simula abertura de semana (Sexta 00h) - Criação em lote + Rollover")
    p_abrir.add_argument("--data", help="Segunda-feira de referência (ex: 2026-10-26)")

    # Subcomando fechar-semana (Terça 01h)
    p_fechar = subparsers.add_parser("fechar-semana", help="Simula fechamento de semana (Terça 01h) - Ausências + Advertências + Auditoria")
    p_fechar.add_argument("--data", help="Segunda-feira de referência (ex: 2026-10-26)")

    # Subcomando reset-execucao
    p_reset = subparsers.add_parser("reset-execucao", help="Remove flag de execução da semana para permitir novo teste")
    p_reset.add_argument("--data", help="Segunda-feira de referência (ex: 2026-10-26)")

    # Subcomando avancar-ciclo
    subparsers.add_parser(
        "avancar-ciclo",
        help="Desloca o ciclo atual 7 dias para trás, consolida tarefas concluídas e cria a nova weekly vigente com rollover",
    )

    args = parser.parse_args()

    with SessionLocal() as db:
        if args.comando == "status":
            cmd_status(db, args)
        elif args.comando == "abrir-semana":
            cmd_abrir_semana(db, args)
        elif args.comando == "fechar-semana":
            cmd_fechar_semana(db, args)
        elif args.comando == "reset-execucao":
            cmd_reset_execucao(db, args)
        elif args.comando == "avancar-ciclo":
            cmd_avancar_ciclo(db, args)


if __name__ == "__main__":
    main()
