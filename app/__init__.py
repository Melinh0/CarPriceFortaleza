import os

from flask import Flask


def create_app(config: dict | None = None) -> Flask:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(base_dir)
    app = Flask(
        __name__,
        template_folder=os.path.join(root_dir, "templates"),
        static_folder=os.path.join(root_dir, "static"),
    )
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "carprice-dev-key")
    app.config["DATA_DIR"] = os.path.join(base_dir, "data")
    app.config["CACHE_DIR"] = os.path.join(app.config["DATA_DIR"], "cache")
    os.makedirs(app.config["CACHE_DIR"], exist_ok=True)

    from . import routes

    app.register_blueprint(routes.bp)

    @app.template_filter("brl")
    def brl_filter(valor) -> str:
        if valor is None:
            return "—"
        try:
            texto = f"{float(valor):,.2f}"
        except (TypeError, ValueError):
            return "—"
        return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")

    return app
