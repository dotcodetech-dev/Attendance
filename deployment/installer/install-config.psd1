# Optional answers for INSTALL.cmd. Any value left empty ('') is asked
# interactively (press Enter to accept the default shown). Fill everything in
# to run the installer fully unattended.
@{
    # Where Aveon is installed. Default: C:\Aveon
    InstallDir    = ''

    # SQL Server. If no SQL Server is installed on this machine, SQL Server
    # Express is installed automatically with the 'sa' password below.
    SqlHost       = ''      # default: localhost. Also accepts host\INSTANCE (e.g. localhost\SQLEXPRESS)
    SqlPort       = ''      # default: 1433
    SqlDatabase   = ''      # default: Aveon
    SqlInstance   = ''      # when several local instances exist: MSSQLSERVER / SQLEXPRESS / <name>
    SqlUser       = ''      # default: sa
    SqlPassword   = ''      # password (for a new SQL Express: min 8 chars, upper+lower+digit+symbol)
    # If the SQL login fails and your Windows account is not a SQL admin, install a
    # separate SQL Express instance 'AVEON' for Aveon? 'Y' or 'N' (blank = ask).
    InstallOwnInstance = ''

    # Web UI administrator password (user name is 'admin').
    AdminPassword = ''

    # LAN IP / host name that devices and browsers use to reach this server.
    # Default: auto-detected IPv4 address.
    ServerAddress = ''

    # IIS site name and port.
    SiteName      = ''      # default: Aveon
    SitePort      = ''      # default: 80
}
