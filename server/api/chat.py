import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..db.orm import Conversation
from ..services.chat_service import ChatService
from .models import ConversationCreate, MessageSend

router = APIRouter(prefix="/chat", tags=["chat"])
_service = ChatService()


def _conv_to_dict(conv: Conversation, include_messages: bool = False) -> dict:
    data = {
        "id": conv.id,
        "persona_id": conv.persona_id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }
    if include_messages:
        data["messages"] = [_msg_to_dict(m) for m in conv.messages]
    return data


def _msg_to_dict(msg) -> dict:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "role": msg.role,
        "content": msg.content,
        "tokens": msg.tokens,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


@router.post("/conversations", summary="创建对话", description="创建一个新的对话会话,可指定关联的 Persona 和标题")
async def create_conversation(body: ConversationCreate):
    conv = await _service.create_conversation(body.persona_id, body.title)
    return {"ok": True, "data": _conv_to_dict(conv), "error": None}


@router.get("/conversations", summary="列出对话", description="列出所有对话会话,按更新时间倒序返回")
async def list_conversations():
    convs = await _service.list_conversations()
    return {"ok": True, "data": [_conv_to_dict(c) for c in convs], "error": None}


@router.get("/conversations/{conversation_id}", summary="获取对话详情", description="获取指定对话的详情,包含其下所有消息")
async def get_conversation(conversation_id: int):
    conv = await _service.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Conversation not found"},
        )
    return {"ok": True, "data": _conv_to_dict(conv, include_messages=True), "error": None}


@router.delete("/conversations/{conversation_id}", summary="删除对话", description="删除指定对话及其所有消息")
async def delete_conversation(conversation_id: int):
    deleted = await _service.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Conversation not found"},
        )
    return {"ok": True, "data": None, "error": None}


@router.post("/conversations/{conversation_id}/messages", summary="发送消息(SSE 流)", description="向指定对话发送消息,并以 SSE 流式返回 AI 回复")
async def send_message(conversation_id: int, body: MessageSend):
    async def event_stream():
        async for event in _service.stream_reply(conversation_id, body.content):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/conversations/{conversation_id}/messages", summary="列出消息", description="列出指定对话下的所有消息历史")
async def list_messages(conversation_id: int):
    messages = await _service.list_messages(conversation_id)
    return {"ok": True, "data": [_msg_to_dict(m) for m in messages], "error": None}
