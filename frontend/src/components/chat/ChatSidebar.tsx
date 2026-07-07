import { useState } from 'react';
import type { ChatSessionItem } from '../../api/types';

interface Props {
  sessions: ChatSessionItem[];
  activeId: number | null;
  loading?: boolean;
  onNewChat: () => void;
  onSelect: (id: number) => void;
  onRename: (id: number, title: string) => void;
  onArchive: (id: number, archived: boolean) => void;
  onDelete: (id: number) => void;
}

/**
 * ChatGPT-style session list: new chat, per-session rename/archive/delete,
 * and a collapsible group for archived conversations.
 */
export default function ChatSidebar({
  sessions,
  activeId,
  loading,
  onNewChat,
  onSelect,
  onRename,
  onArchive,
  onDelete,
}: Props) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [showArchived, setShowArchived] = useState(false);

  const active = sessions.filter((s) => !s.archived);
  const archived = sessions.filter((s) => s.archived);

  const commitRename = (id: number) => {
    const title = editTitle.trim();
    setEditingId(null);
    if (title) onRename(id, title);
  };

  const renderItem = (session: ChatSessionItem) => {
    const isActive = session.id === activeId;
    const isEditing = session.id === editingId;
    return (
      <li key={session.id} className={isActive ? 'chat-sidebar__item is-active' : 'chat-sidebar__item'}>
        {isEditing ? (
          <input
            className="chat-sidebar__rename"
            value={editTitle}
            autoFocus
            maxLength={200}
            onChange={(e) => setEditTitle(e.target.value)}
            onBlur={() => commitRename(session.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename(session.id);
              if (e.key === 'Escape') setEditingId(null);
            }}
            aria-label="Chat title"
          />
        ) : (
          <>
            <button
              type="button"
              className="chat-sidebar__title"
              title={session.title}
              onClick={() => onSelect(session.id)}
            >
              {session.title}
            </button>
            <span className="chat-sidebar__actions">
              <button
                type="button"
                className="chat-sidebar__action"
                title="Rename"
                aria-label={`Rename chat ${session.title}`}
                onClick={() => {
                  setEditingId(session.id);
                  setEditTitle(session.title);
                }}
              >
                ✎
              </button>
              <button
                type="button"
                className="chat-sidebar__action"
                title={session.archived ? 'Unarchive' : 'Archive'}
                aria-label={`${session.archived ? 'Unarchive' : 'Archive'} chat ${session.title}`}
                onClick={() => onArchive(session.id, !session.archived)}
              >
                {session.archived ? '↩' : '🗄'}
              </button>
              <button
                type="button"
                className="chat-sidebar__action chat-sidebar__action--danger"
                title="Delete"
                aria-label={`Delete chat ${session.title}`}
                onClick={() => {
                  if (window.confirm(`Delete chat "${session.title}"? This cannot be undone.`)) {
                    onDelete(session.id);
                  }
                }}
              >
                🗑
              </button>
            </span>
          </>
        )}
      </li>
    );
  };

  return (
    <aside className="chat-sidebar card">
      <button type="button" className="btn btn--primary btn--block" onClick={onNewChat}>
        + New chat
      </button>

      {loading && <p className="muted chat-sidebar__status">Loading chats…</p>}
      {!loading && sessions.length === 0 && (
        <p className="muted chat-sidebar__status">No chats yet. Ask your first question!</p>
      )}

      <ul className="chat-sidebar__list">{active.map(renderItem)}</ul>

      {archived.length > 0 && (
        <div className="chat-sidebar__archived">
          <button
            type="button"
            className="chat-sidebar__group-toggle"
            onClick={() => setShowArchived((v) => !v)}
            aria-expanded={showArchived}
          >
            {showArchived ? '▾' : '▸'} Archived ({archived.length})
          </button>
          {showArchived && <ul className="chat-sidebar__list">{archived.map(renderItem)}</ul>}
        </div>
      )}
    </aside>
  );
}
