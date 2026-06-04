import uuid
from dataclasses import dataclass

from flask import Blueprint, jsonify, request


@dataclass
class AssistantRouteServices:
    ai_assistant_config: object
    ai_executable_route_answer: object
    ai_latest_conversation_id: object
    ai_local_assistant_payload: object
    ai_provider_answer: object
    ai_recent_chat_messages: object
    ai_safe_text: object
    ai_store_chat_message: object
    get_logged_in_user: object
    is_logged_in: object
    history_limit: object


def create_assistant_blueprint(services):
    bp = Blueprint("assistant_api", __name__)

    def history_limit():
        value = services.history_limit
        return value() if callable(value) else value

    @bp.route("/api/assistant/chat", methods=["POST"])
    def assistant_chat_api():
        if not services.is_logged_in():
            return jsonify({"error": "\u8bf7\u5148\u767b\u5f55"}), 401
        config = services.ai_assistant_config()
        if not config["enabled"]:
            return jsonify({"error": "AI assistant is disabled"}), 503

        payload = request.get_json(silent=True) or {}
        message = services.ai_safe_text(payload.get("message"), 1200)
        if not message:
            return jsonify({"error": "Please enter a question"}), 400
        page_context = payload.get("page_context") if isinstance(payload.get("page_context"), dict) else {}
        conversation_id = services.ai_safe_text(payload.get("conversation_id"), 80) or str(uuid.uuid4())
        current_user = services.get_logged_in_user()
        user_id = current_user["id"] if current_user else 0
        history = services.ai_recent_chat_messages(user_id, conversation_id, limit=history_limit())

        local_payload = services.ai_local_assistant_payload(message, page_context, history)
        provider = "local"
        model_error = ""
        executable_route_answer = services.ai_executable_route_answer(local_payload)
        if executable_route_answer:
            local_payload["answer"] = executable_route_answer
        else:
            try:
                model_answer = services.ai_provider_answer(message, page_context, local_payload, history)
            except Exception as exc:
                model_answer = None
                model_error = f"{type(exc).__name__}: {exc}"
            if model_answer:
                local_payload["answer"] = model_answer
                provider = config["provider"]

        services.ai_store_chat_message(user_id, conversation_id, "user", message)
        response_payload = {
            "conversation_id": conversation_id,
            "provider": provider,
            "model": config["model"] if provider != "local" else "",
            "mode": local_payload.get("mode", "general"),
            "modules": local_payload.get("modules", []),
            "routing": local_payload.get("routing", {}),
            "answer": local_payload["answer"],
            "cards": local_payload.get("cards", []),
            "actions": local_payload.get("actions", []),
            "suggestions": local_payload.get("suggestions", []),
            "model_error": model_error,
        }
        services.ai_store_chat_message(user_id, conversation_id, "assistant", local_payload["answer"], response_payload)

        return jsonify(response_payload)

    @bp.route("/api/assistant/history")
    def assistant_history_api():
        if not services.is_logged_in():
            return jsonify({"error": "\u8bf7\u5148\u767b\u5f55"}), 401
        current_user = services.get_logged_in_user()
        user_id = current_user["id"] if current_user else 0
        conversation_id = services.ai_safe_text(request.args.get("conversation_id"), 80)
        if not conversation_id:
            conversation_id = services.ai_latest_conversation_id(user_id)
        if not conversation_id:
            return jsonify({"conversation_id": "", "messages": []})

        messages = services.ai_recent_chat_messages(user_id, conversation_id, limit=60)
        return jsonify({
            "conversation_id": conversation_id,
            "messages": messages,
        })

    return bp
