"""The /v1/host routes of the connection page, one POST each, served by the HostConnections methods."""


def mount_host_routes(app, connections):
    for path, handler in (("discover", connections.discover), ("status", connections.status),
                          ("models", connections.models), ("login", connections.login), ("select", connections.select),
                          ("detach", connections.detach), ("cancel-login", connections.cancel_login),
                          ("install", connections.install_cli), ("cancel-install", connections.cancel_install),
                          ("release-check", connections.release_check),
                          ("enable", connections.enable), ("login-code", connections.send_login_code),
                          ("logout", connections.logout), ("clear-data", connections.clear_data)):
        app.add_api_route(f"/v1/host/{path}", handler, methods=["POST"])
