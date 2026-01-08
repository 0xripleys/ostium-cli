"""Main entry point for Ostium CLI."""

import typer

from ostium_cli.commands.cancel import cancel as cancel_command
from ostium_cli.commands.close import close as close_command
from ostium_cli.commands.limit import limit as limit_command
from ostium_cli.commands.market import market as market_command
from ostium_cli.commands.orders import orders as orders_command
from ostium_cli.commands.stoploss import stoploss as stoploss_command
from ostium_cli.commands.trades import trades as trades_command

app = typer.Typer(
    name="ostium",
    help="CLI for Ostium decentralized perpetuals exchange",
    no_args_is_help=True,
)

# Register commands
app.command("trades")(trades_command)
app.command("orders")(orders_command)
app.command("market")(market_command)
app.command("limit")(limit_command)
app.command("stoploss")(stoploss_command)
app.command("cancel")(cancel_command)
app.command("close")(close_command)


if __name__ == "__main__":
    app()
