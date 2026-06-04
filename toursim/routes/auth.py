from dataclasses import dataclass

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash


@dataclass
class AuthRouteServices:
    create_user: object
    get_db_connection: object
    get_logged_in_user: object
    get_user_activity_stats: object
    get_user_avatar_url: object
    get_user_by_id: object
    get_user_by_username: object
    is_logged_in: object
    load_favorite_diaries: object
    load_favorite_foods: object
    load_places: object
    load_user_diaries: object
    save_user_avatar_choice: object
    update_user_account: object
    update_user_avatar_path: object


def create_auth_blueprint(services):
    bp = Blueprint("auth", __name__)

    @bp.route("/")
    def index():
        if services.is_logged_in():
            return redirect(url_for("home"))
        return redirect(url_for("login"))

    @bp.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            confirm_password = request.form.get("confirm_password", "").strip()
            avatar_file = request.files.get("avatar")
            selected_avatar_path = request.form.get("preset_avatar", "").strip()

            if not username or not password or not confirm_password:
                flash("用户名和密码不能为空")
                return render_template("register.html")

            if password != confirm_password:
                flash("两次输入的密码不一致")
                return render_template("register.html")

            user_id = services.create_user(username, password)
            if not user_id:
                flash("用户名已存在，请更换用户名")
                return render_template("register.html")

            avatar_path = services.save_user_avatar_choice(avatar_file, selected_avatar_path, username, user_id)
            services.update_user_avatar_path(user_id, avatar_path)

            flash("注册成功，请登录")
            return redirect(url_for("login"))

        return render_template("register.html")

    @bp.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

            if not username or not password:
                flash("用户名和密码不能为空")
                return render_template("login.html")

            user = services.get_user_by_username(username)

            if user and check_password_hash(user["password"], password):
                session["username"] = user["username"]
                session["avatar_path"] = user["avatar_path"] if "avatar_path" in user.keys() else ""
                return redirect(url_for("home"))

            flash("用户名或密码错误")
            return render_template("login.html")

        return render_template("login.html")

    @bp.route("/home")
    def home():
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))

        current_user = services.get_logged_in_user()
        places_count = 0
        try:
            places_count = len(services.load_places())
        except Exception:
            pass

        diaries_count = 0
        favorites_count = 0
        try:
            conn = services.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM diaries")
            diaries_count = cursor.fetchone()[0]

            if current_user:
                cursor.execute("SELECT COUNT(*) FROM user_favorites WHERE user_id = ?", (current_user["id"],))
                favorites_count = cursor.fetchone()[0]

            conn.close()
        except Exception:
            pass

        return render_template(
            "home.html",
            username=session["username"],
            current_user=current_user,
            current_user_avatar_url=services.get_user_avatar_url(current_user) if current_user else "",
            places_count=places_count,
            diaries_count=diaries_count,
            favorites_count=favorites_count,
        )

    @bp.route("/logout")
    def logout():
        session.pop("username", None)
        flash("你已退出登录")
        return redirect(url_for("login"))

    @bp.route("/profile", methods=["GET", "POST"])
    def profile():
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))

        current_user = services.get_logged_in_user()
        if current_user is None:
            flash("账号不存在，请重新登录")
            session.pop("username", None)
            return redirect(url_for("login"))

        if request.method == "POST":
            action = request.form.get("action", "account").strip().lower()
            if action == "avatar":
                avatar_file = request.files.get("avatar")
                selected_avatar_path = request.form.get("preset_avatar", "").strip()
                if (not avatar_file or not avatar_file.filename) and not selected_avatar_path:
                    flash("请选择头像")
                else:
                    avatar_path = services.save_user_avatar_choice(
                        avatar_file,
                        selected_avatar_path,
                        current_user["username"],
                        current_user["id"],
                    )
                    services.update_user_avatar_path(current_user["id"], avatar_path)
                    session["avatar_path"] = avatar_path
                    flash("头像已更新")
                return redirect(url_for("profile"))

            new_username = request.form.get("username", "").strip()
            current_password = request.form.get("current_password", "").strip()
            new_password = request.form.get("new_password", "").strip()
            confirm_password = request.form.get("confirm_password", "").strip()
            if new_password and new_password != confirm_password:
                flash("两次输入的新密码不一致")
                return redirect(url_for("profile"))
            ok, message = services.update_user_account(
                current_user["id"],
                new_username=new_username,
                current_password=current_password,
                new_password=new_password,
            )
            flash(message)
            if ok:
                session["username"] = new_username
            return redirect(url_for("profile"))

        current_user = services.get_logged_in_user()
        stats = services.get_user_activity_stats(current_user)
        my_diaries = services.load_user_diaries(current_user["username"], limit=6)
        favorite_diaries = services.load_favorite_diaries(current_user["id"], limit=6)
        favorite_foods = services.load_favorite_foods(current_user["id"], limit=6)
        conn = services.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT diary_comments.*, diaries.title AS diary_title
            FROM diary_comments
            LEFT JOIN diaries ON diaries.id = diary_comments.diary_id
            WHERE diary_comments.author = ?
            ORDER BY diary_comments.created_at DESC, diary_comments.id DESC
            LIMIT 5
            """,
            (current_user["username"],)
        )
        recent_comments = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return render_template(
            "profile.html",
            username=current_user["username"],
            current_user=current_user,
            current_user_avatar_url=services.get_user_avatar_url(current_user),
            stats=stats,
            my_diaries=my_diaries,
            favorite_diaries=favorite_diaries,
            favorite_foods=favorite_foods,
            recent_comments=recent_comments,
        )

    @bp.route("/user/<int:user_id>")
    def user_profile(user_id):
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))

        profile_user = services.get_user_by_id(user_id)
        if profile_user is None:
            flash("未找到该用户")
            return redirect(url_for("diaries"))

        current_user = services.get_logged_in_user()
        user_diaries = services.load_user_diaries(profile_user["username"], limit=12)
        stats = services.get_user_activity_stats(profile_user)
        return render_template(
            "user_profile.html",
            username=session["username"],
            current_user=current_user,
            profile_user=profile_user,
            profile_avatar_url=services.get_user_avatar_url(profile_user),
            stats=stats,
            user_diaries=user_diaries,
            is_self=current_user and current_user["id"] == profile_user["id"],
        )

    return bp
