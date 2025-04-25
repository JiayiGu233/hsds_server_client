import typer
from hsds_client.core import HSDSClient
from hsds_client.config import load_config, save_config

app = typer.Typer(help="📦 HSDS CLI 工具，用于访问并分析 .strc 数据文件")
config_app = typer.Typer(help="⚙️ 配置命令（设置和获取 MPC 地址）")
app.add_typer(config_app, name="config")

DEFAULT_PORT = 5101

@app.command(help="📄 列出所有可用的 .strc 数据文件")
def list(ip: str = typer.Option(None, "--ip", help="MPC 服务器 IP 地址（可选）")):
    """
    使用指定 IP 或保存的配置，列出所有可访问的 HSDS .strc 文件。
    """
    if ip:
        endpoint = f"http://{ip}:{DEFAULT_PORT}"
    else:
        cfg = load_config()
        endpoint = cfg.get("endpoint")

    if not endpoint:
        typer.echo("❌ Endpoint 未设置。请使用 --ip 或先运行 `hscli config set-mpc-address <ip>`")
        raise typer.Exit(1)

    client = HSDSClient(endpoint)
    for f in client.list_all_files_name():
        typer.echo(f)

@config_app.command("get-mpc-address", help="🔍 查看当前 MPC 地址设置")
def get_mpc_address():
    cfg = load_config()
    endpoint = cfg.get("endpoint")
    if endpoint:
        typer.echo(f"🔍 当前 MPC 地址: {endpoint}")
    else:
        typer.echo("⚠️  还没有设置 MPC 地址")

@config_app.command("set-mpc-address", help="🛠️ 设置 MPC IP 地址（例如 10.86.18.139）")
def set_mpc_address(ip: str, force: bool = typer.Option(False, "--force", help="如果已设置则强制覆盖")):
    cfg = load_config()
    endpoint = f"http://{ip}:{DEFAULT_PORT}"

    if cfg.get("endpoint") and not force:
        typer.echo("⚠️  已经设置了 MPC 地址。如需覆盖请加 --force")
        raise typer.Exit(code=1)

    save_config({"endpoint": endpoint})
    typer.echo(f"✅ MPC 地址已保存为: {endpoint}")

def main():
    app()
