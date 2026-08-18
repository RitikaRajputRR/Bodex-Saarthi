import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import "./App.css";

// ==========================================
// RENDER BACKEND URL
// ==========================================

const BACKEND_URL =
  "https://bodex-saarthi-backend.onrender.com";

function App() {
  // ==========================================
  // CHAT STATE
  // ==========================================

  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  // ==========================================
  // SIDEBAR / HISTORY
  // ==========================================

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [history, setHistory] = useState([]);

  const [activeChatId, setActiveChatId] = useState(null);

  // ==========================================
  // READ ALOUD
  // ==========================================

  const [speakingIndex, setSpeakingIndex] = useState(null);

  // ==========================================
  // FILE STATE
  // ==========================================

  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedFileUrl, setSelectedFileUrl] = useState(null);

  const fileInputRef = useRef(null);

  // ==========================================
  // CHAT REFS
  // ==========================================

  const messagesContainerRef = useRef(null);
  const messagesEndRef = useRef(null);

  // ==========================================
  // LOAD HISTORY
  // ==========================================

  useEffect(() => {
    try {
      const savedHistory = localStorage.getItem(
        "saarthi-chat-history"
      );

      if (savedHistory) {
        const parsedHistory = JSON.parse(savedHistory);

        if (Array.isArray(parsedHistory)) {
          setHistory(parsedHistory);
        }
      }
    } catch (error) {
      console.error("History load error:", error);
    }
  }, []);

  // ==========================================
  // SAVE / UPDATE CURRENT CHAT HISTORY
  // ==========================================

  useEffect(() => {
    if (messages.length === 0) return;

    const firstUserMessage = messages.find(
      (msg) => msg.role === "user"
    );

    if (!firstUserMessage) return;

    const chatId = activeChatId || Date.now();

    if (!activeChatId) {
      setActiveChatId(chatId);
    }

    const title =
      firstUserMessage.content?.trim() ||
      "New Chat";

    const chat = {
      id: chatId,
      title: title.substring(0, 45),
      messages: messages,
      createdAt: new Date().toISOString(),
    };

    setHistory((prev) => {
      const existingChatIndex = prev.findIndex(
        (item) => item.id === chatId
      );

      let updated;

      // ========================================
      // EXISTING CHAT UPDATE
      // ========================================

      if (existingChatIndex !== -1) {
        updated = [...prev];

        updated[existingChatIndex] = {
          ...updated[existingChatIndex],
          title: chat.title,
          messages: chat.messages,
        };
      }

      // ========================================
      // NEW CHAT
      // ========================================

      else {
        updated = [chat, ...prev];
      }

      localStorage.setItem(
        "saarthi-chat-history",
        JSON.stringify(updated)
      );

      return updated;
    });
  }, [messages, activeChatId]);

  // ==========================================
  // AUTO SCROLL
  // ==========================================

  useEffect(() => {
    const container = messagesContainerRef.current;

    if (!container) return;

    const distanceFromBottom =
      container.scrollHeight -
      container.scrollTop -
      container.clientHeight;

    const isNearBottom = distanceFromBottom < 180;

    if (isNearBottom) {
      messagesEndRef.current?.scrollIntoView({
        behavior: "auto",
        block: "end",
      });
    }
  }, [messages]);

  // ==========================================
  // IMAGE PREVIEW
  // ==========================================

  useEffect(() => {
    if (!selectedFile) {
      setSelectedFileUrl(null);
      return;
    }

    if (selectedFile.type.startsWith("image/")) {
      const url = URL.createObjectURL(selectedFile);

      setSelectedFileUrl(url);

      return () => {
        URL.revokeObjectURL(url);
      };
    }

    setSelectedFileUrl(null);
  }, [selectedFile]);

  // ==========================================
  // CLEAN AI RESPONSE
  // ==========================================

  const cleanAIResponse = (text) => {
    if (!text) return "";

    return text
      .replace(/â/g, "-")
      .replace(/â/g, "-")
      .replace(/â/g, "'")
      .replace(/â/g, "'")
      .replace(/â/g, '"')
      .replace(/â/g, '"')
      .replace(/\\\\+/g, "\\");
  };

  // ==========================================
  // NEW CHAT
  // ==========================================

  const clearChat = () => {
    window.speechSynthesis.cancel();
    setSpeakingIndex(null);

    setMessages([]);
    setMessage("");

    setSelectedFile(null);
    setSelectedFileUrl(null);

    setActiveChatId(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // ==========================================
  // CLEAR ALL CHAT HISTORY
  // ==========================================

  const clearAllHistory = () => {
    if (history.length === 0) return;

    const confirmClear = window.confirm(
      "Are you sure you want to clear all chat history?"
    );

    if (!confirmClear) return;

    setHistory([]);
    setMessages([]);
    setActiveChatId(null);

    localStorage.removeItem(
      "saarthi-chat-history"
    );

    window.speechSynthesis.cancel();
    setSpeakingIndex(null);
  };

  // ==========================================
  // LOAD OLD CHAT
  // ==========================================

  const loadHistory = (chat) => {
    window.speechSynthesis.cancel();
    setSpeakingIndex(null);

    setActiveChatId(chat.id);

    setMessages(chat.messages || []);

    if (window.innerWidth <= 768) {
      setSidebarOpen(false);
    }
  };

  // ==========================================
  // DELETE SINGLE HISTORY
  // ==========================================

  const deleteHistory = (id, event) => {
    event.stopPropagation();

    const updated = history.filter(
      (item) => item.id !== id
    );

    setHistory(updated);

    localStorage.setItem(
      "saarthi-chat-history",
      JSON.stringify(updated)
    );

    if (activeChatId === id) {
      setActiveChatId(null);
      setMessages([]);
    }
  };

  // ==========================================
  // READ ALOUD
  // ==========================================

  const readAloud = (text, index) => {
    if (!text) return;

    if (
      speakingIndex === index &&
      window.speechSynthesis.speaking
    ) {
      window.speechSynthesis.cancel();
      setSpeakingIndex(null);
      return;
    }

    window.speechSynthesis.cancel();
    setSpeakingIndex(null);

    const cleanText = text
      .replace(/#{1,6}\s?/g, "")
      .replace(/\*\*(.*?)\*\*/g, "$1")
      .replace(/\*(.*?)\*/g, "$1")
      .replace(/__(.*?)__/g, "$1")
      .replace(/_(.*?)_/g, "$1")
      .replace(/`(.*?)`/g, "$1")
      .replace(/\[(.*?)\]\([^)]+\)/g, "$1")
      .replace(/https?:\/\/\S+/g, "")
      .replace(/\n+/g, " ")
      .trim();

    if (!cleanText) return;

    const utterance =
      new SpeechSynthesisUtterance(cleanText);

    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 1;

    utterance.onstart = () => {
      setSpeakingIndex(index);
    };

    utterance.onend = () => {
      setSpeakingIndex(null);
    };

    utterance.onerror = () => {
      setSpeakingIndex(null);
    };

    window.speechSynthesis.speak(utterance);
  };

  // ==========================================
  // STOP READ ALOUD
  // ==========================================

  const stopReading = () => {
    window.speechSynthesis.cancel();
    setSpeakingIndex(null);
  };

  // ==========================================
  // COPY MESSAGE
  // ==========================================

  const copyMessage = async (text, index) => {
    try {
      await navigator.clipboard.writeText(text);

      setMessages((prev) =>
        prev.map((msg, i) =>
          i === index
            ? {
                ...msg,
                copied: true,
              }
            : msg
        )
      );

      setTimeout(() => {
        setMessages((prev) =>
          prev.map((msg, i) =>
            i === index
              ? {
                  ...msg,
                  copied: false,
                }
              : msg
          )
        );
      }, 2000);
    } catch (error) {
      console.error("Copy failed:", error);
    }
  };

  // ==========================================
  // URL CHECK
  // ==========================================

  const isUrl = (text) => {
    if (!text) return false;

    try {
      const url = new URL(text.trim());

      return (
        url.protocol === "http:" ||
        url.protocol === "https:"
      );
    } catch {
      return false;
    }
  };

  // ==========================================
  // FILE SELECT
  // ==========================================

  const handleFileSelect = (event) => {
    const file = event.target.files?.[0];

    if (!file) return;

    const allowedTypes = [
      "application/pdf",
      "image/jpeg",
      "image/png",
      "image/webp",
      "image/jpg",
    ];

    if (!allowedTypes.includes(file.type)) {
      alert("Please select a PDF or image file.");

      event.target.value = "";
      return;
    }

    if (file.size > 20 * 1024 * 1024) {
      alert("File size must be less than 20 MB.");

      event.target.value = "";
      return;
    }

    setSelectedFile(file);
  };

  // ==========================================
  // REMOVE FILE
  // ==========================================

  const removeFile = () => {
    setSelectedFile(null);
    setSelectedFileUrl(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // ==========================================
  // UPDATE LAST ASSISTANT MESSAGE
  // ==========================================

  const updateLastAssistantMessage = (
    content,
    extra = {}
  ) => {
    setMessages((prev) => {
      const updated = [...prev];

      const lastIndex = updated.length - 1;

      if (
        updated[lastIndex]?.role === "assistant"
      ) {
        updated[lastIndex] = {
          ...updated[lastIndex],
          content,
          ...extra,
        };
      }

      return updated;
    });
  };

  // ==========================================
  // SEND MESSAGE
  // ==========================================

  const sendMessage = async () => {
    if (
      (!message.trim() && !selectedFile) ||
      loading
    ) {
      return;
    }

    const userMessage = message.trim();
    const fileToSend = selectedFile;

    // ========================================
    // CREATE CHAT ID
    // ========================================

    if (!activeChatId) {
      setActiveChatId(Date.now());
    }

    // ========================================
    // FILE PREVIEW
    // ========================================

    let filePreview = null;

    if (fileToSend) {
      let previewUrl = null;

      if (fileToSend.type.startsWith("image/")) {
        previewUrl =
          URL.createObjectURL(fileToSend);
      }

      filePreview = {
        name: fileToSend.name,
        type: fileToSend.type,
        size: fileToSend.size,
        url: previewUrl,
      };
    }

    // ========================================
    // URL DETECTION
    // ========================================

    const messageIsUrl = isUrl(userMessage);

    // ========================================
    // USER MESSAGE
    // ========================================

    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content:
          userMessage ||
          "Please analyze this file.",
        file: filePreview,
        isUrl: messageIsUrl,
      },
    ]);

    // ========================================
    // CLEAR INPUT
    // ========================================

    setMessage("");
    setSelectedFile(null);
    setSelectedFileUrl(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }

    setLoading(true);

    // ========================================
    // EMPTY AI MESSAGE
    // ========================================

    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        content: "",
        time: null,
        streaming: true,
        copied: false,
      },
    ]);

    const startTime = performance.now();

    try {
      // ======================================
      // FORM DATA
      // ======================================

      const formData = new FormData();

      formData.append("message", userMessage);

      if (fileToSend) {
        formData.append("file", fileToSend);
      }

      // ======================================
      // RENDER BACKEND
      // ======================================

      const response = await fetch(
        `${BACKEND_URL}/chat`,
        {
          method: "POST",
          body: formData,
        }
      );

      // ======================================
      // SERVER ERROR
      // ======================================

      if (!response.ok) {
        let errorMessage = "Server error";

        try {
          const errorData =
            await response.json();

          if (errorData?.error) {
            errorMessage =
              typeof errorData.error === "string"
                ? errorData.error
                : JSON.stringify(
                    errorData.error
                  );
          }
        } catch {
          // Ignore JSON parsing error
        }

        throw new Error(errorMessage);
      }

      // ======================================
      // STREAM CHECK
      // ======================================

      if (!response.body) {
        throw new Error(
          "Streaming is not supported by this browser."
        );
      }

      const reader = response.body.getReader();

      const decoder = new TextDecoder("utf-8");

      let fullResponse = "";
      let buffer = "";
      let backendTime = null;

      // ======================================
      // STREAM
      // ======================================

      while (true) {
        const { value, done } =
          await reader.read();

        if (done) break;

        buffer += decoder.decode(value, {
          stream: true,
        });

        // ====================================
        // ERROR MARKER
        // ====================================

        const errorMarker = "__ERROR__:";

        const errorIndex =
          buffer.indexOf(errorMarker);

        if (errorIndex !== -1) {
          const textBeforeError =
            buffer.substring(0, errorIndex);

          if (textBeforeError) {
            fullResponse += textBeforeError;
          }

          const errorText =
            buffer.substring(
              errorIndex +
                errorMarker.length
            );

          throw new Error(
            errorText ||
              "Backend processing error."
          );
        }

        // ====================================
        // TIME MARKER
        // ====================================

        const timeMarker = "__TIME__:";

        const timeIndex =
          buffer.indexOf(timeMarker);

        if (timeIndex !== -1) {
          const textBeforeTime =
            buffer.substring(0, timeIndex);

          if (textBeforeTime) {
            fullResponse += textBeforeTime;
          }

          const timeValue =
            buffer.substring(
              timeIndex +
                timeMarker.length
            );

          const timeMatch =
            timeValue.match(
              /\d+(\.\d+)?/
            );

          backendTime =
            timeMatch
              ? timeMatch[0]
              : null;

          buffer = "";

          updateLastAssistantMessage(
            cleanAIResponse(fullResponse),
            {
              streaming: true,
            }
          );

          continue;
        }

        // ====================================
        // NORMAL STREAM
        // ====================================

        if (buffer) {
          fullResponse += buffer;
          buffer = "";

          updateLastAssistantMessage(
            cleanAIResponse(fullResponse),
            {
              streaming: true,
            }
          );
        }
      }

      // ======================================
      // FRONTEND TIME
      // ======================================

      const endTime = performance.now();

      const frontendTime = (
        (endTime - startTime) /
        1000
      ).toFixed(2);

      // ======================================
      // FINAL RESPONSE
      // ======================================

      const finalResponse =
        cleanAIResponse(fullResponse);

      updateLastAssistantMessage(
        finalResponse ||
          "I couldn't generate a response.",
        {
          time:
            backendTime ||
            frontendTime,
          streaming: false,
          copied: false,
        }
      );
    } catch (error) {
      console.error("Chat error:", error);

      updateLastAssistantMessage(
        error.message ||
          "Unable to connect to the AI server.",
        {
          streaming: false,
          time: null,
          copied: false,
        }
      );
    } finally {
      setLoading(false);
    }
  };

  // ==========================================
  // ENTER KEY
  // ==========================================

  const handleKeyDown = (event) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {
      event.preventDefault();
      sendMessage();
    }
  };

  // ==========================================
  // UI
  // ==========================================

  return (
    <div className="chat-app">

      {/* ======================================
          SIDEBAR
      ====================================== */}

      <aside
        className={`sidebar ${
          sidebarOpen
            ? "sidebar-open"
            : "sidebar-closed"
        }`}
      >

        {/* SIDEBAR TOP */}

        <div className="sidebar-top">

          <div className="sidebar-brand">

            <img
              src="/Saarthi.jpeg"
              alt="Saarthi"
              className="sidebar-logo"
            />

            <div>
              <h2>Saarthi</h2>
              <span>AI Assistant</span>
            </div>

          </div>

          <button
            className="close-sidebar-btn"
            onClick={() =>
              setSidebarOpen(false)
            }
            type="button"
          >
            ×
          </button>

        </div>

        {/* NEW CHAT */}

        <button
          className="sidebar-new-chat"
          onClick={clearChat}
          type="button"
        >
          <span>＋</span>
          New Chat
        </button>

        {/* HISTORY */}

        <div className="sidebar-history">

          <div className="history-heading">

            <span>Chat History</span>

            <button
              className="clear-history-btn"
              onClick={clearAllHistory}
              disabled={history.length === 0}
              title="Clear all chat history"
              type="button"
            >
              🗑 Clear
            </button>

          </div>

          {history.length === 0 ? (

            <div className="no-history">
              No previous chats
            </div>

          ) : (

            history.map((chat) => (

              <button
                key={chat.id}
                className={`history-item ${
                  activeChatId === chat.id
                    ? "active-history"
                    : ""
                }`}
                onClick={() =>
                  loadHistory(chat)
                }
                type="button"
              >

                <span className="history-chat-icon">
                  💬
                </span>

                <span className="history-title">
                  {chat.title}
                </span>

                <span
                  className="delete-history"
                  onClick={(event) =>
                    deleteHistory(
                      chat.id,
                      event
                    )
                  }
                  title="Delete"
                >
                  ×
                </span>

              </button>

            ))

          )}

        </div>

        {/* SIDEBAR BOTTOM */}

        <div className="sidebar-bottom">
          <span>© Saarthi AI</span>
        </div>

      </aside>

      {/* ======================================
          MAIN CHAT
      ====================================== */}

      <div className="chat-main">

        {/* HEADER */}

        <header className="chat-header">

          <div className="header-left">

            {!sidebarOpen && (

              <button
                className="menu-btn"
                onClick={() =>
                  setSidebarOpen(true)
                }
                type="button"
              >
                ☰
              </button>

            )}

            <img
              src="/Saarthi.jpeg"
              alt="Saarthi"
              className="ai-logo"
            />

            <div className="saarthi-title">

              <h1>Saarthi</h1>

              <p>
                AI Assistant
              </p>

            </div>

          </div>

          <button
            className="new-chat-btn"
            onClick={clearChat}
            type="button"
          >
            ＋ New Chat
          </button>

        </header>

        {/* MESSAGES */}

        <main
          ref={messagesContainerRef}
          className="chat-messages"
        >

          {messages.length === 0 ? (

            <div className="welcome">

              <div className="welcome-icon">

                <img
                  src="/Saarthi.jpeg"
                  alt="Saarthi"
                  className="welcome-logo"
                />

              </div>

              <h2>
                How can I help you?
              </h2>

              <p>
                Ask me anything, paste a URL,
                or upload a PDF/image.
              </p>

            </div>

          ) : (

            messages.map((msg, index) => (

              <div
                key={index}
                className={`message-wrapper ${msg.role}`}
              >

                {/* SENDER */}

                <div className="sender">

                  {msg.role === "user" ? (

                    "👤 You"

                  ) : (

                    <>
                      <img
                        src="/Saarthi.jpeg"
                        alt="Saarthi"
                        className="sender-image"
                      />

                      <span className="saarthi-name">
                        Saarthi
                      </span>
                    </>

                  )}

                </div>

                {/* URL */}

                {msg.role === "user" &&
                  msg.isUrl && (

                    <div className="uploaded-file">

                      <div className="file-icon">
                        🌐
                      </div>

                      <div className="file-details">

                        <strong>
                          Website URL
                        </strong>

                        <span>
                          URL will be analyzed
                        </span>

                      </div>

                    </div>

                  )}

                {/* FILE */}

                {msg.role === "user" &&
                  msg.file && (

                    <div className="uploaded-file">

                      {msg.file.type ===
                      "application/pdf" ? (

                        <div className="file-icon">
                          📄
                        </div>

                      ) : (

                        <img
                          src={msg.file.url}
                          alt={msg.file.name}
                          className="uploaded-image"
                        />

                      )}

                      <div className="file-details">

                        <strong>
                          {msg.file.name}
                        </strong>

                        <span>
                          {msg.file.type ===
                          "application/pdf"
                            ? "PDF Document"
                            : "Image"}
                        </span>

                      </div>

                    </div>

                  )}

                {/* MESSAGE */}

                <div className="message">

                  {msg.role === "assistant" ? (

                    <ReactMarkdown
                      remarkPlugins={[
                        remarkGfm,
                      ]}
                    >
                      {msg.content}
                    </ReactMarkdown>

                  ) : (

                    <p>
                      {msg.content}
                    </p>

                  )}

                  {msg.role === "assistant" &&
                    msg.streaming && (

                      <span className="streaming-cursor">
                        ▌
                      </span>

                    )}

                </div>

                {/* ACTIONS */}

                {msg.role === "assistant" &&
                  !msg.streaming &&
                  msg.content && (

                    <div className="message-actions">

                      {/* COPY */}

                      <button
                        className="action-btn"
                        onClick={() =>
                          copyMessage(
                            msg.content,
                            index
                          )
                        }
                        type="button"
                        title="Copy"
                      >
                        ⧉

                        {msg.copied && (
                          <span>
                            Copied
                          </span>
                        )}

                      </button>

                      {/* READ ALOUD */}

                      <button
                        className={`action-btn ${
                          speakingIndex ===
                          index
                            ? "reading"
                            : ""
                        }`}
                        onClick={() =>
                          readAloud(
                            msg.content,
                            index
                          )
                        }
                        type="button"
                        title={
                          speakingIndex ===
                          index
                            ? "Stop reading"
                            : "Read aloud"
                        }
                      >

                        {speakingIndex ===
                        index
                          ? "⏹"
                          : "🔊"}

                        <span>
                          {speakingIndex ===
                          index
                            ? "Stop"
                            : "Read aloud"}
                        </span>

                      </button>

                      {/* TIME */}

                      {msg.time && (

                        <span className="response-time">
                          ◷ {msg.time}s
                        </span>

                      )}

                    </div>

                  )}

              </div>

            ))

          )}

          <div ref={messagesEndRef} />

        </main>

        {/* INPUT AREA */}

        <div className="chat-input-container">

          {/* SELECTED FILE */}

          {selectedFile && (

            <div className="selected-file">

              {selectedFile.type ===
              "application/pdf" ? (

                <div className="selected-file-icon">
                  📄
                </div>

              ) : (

                <img
                  src={selectedFileUrl}
                  alt="Preview"
                  className="selected-image"
                />

              )}

              <div className="selected-file-info">

                <strong>
                  {selectedFile.name}
                </strong>

                <span>
                  {(
                    selectedFile.size /
                    1024 /
                    1024
                  ).toFixed(2)}
                  MB
                </span>

              </div>

              <button
                className="remove-file-btn"
                onClick={removeFile}
                type="button"
                title="Remove file"
              >
                ×
              </button>

            </div>

          )}

          {/* INPUT */}

          <div className="chat-input">

            {/* UPLOAD */}

            <button
              className="inside-icon-btn"
              type="button"
              title="Upload PDF or Image"
              onClick={() =>
                fileInputRef.current?.click()
              }
              disabled={loading}
            >
              +
            </button>

            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.webp"
              onChange={handleFileSelect}
              hidden
            />

            {/* MESSAGE */}

            <input
              type="text"
              placeholder="Message Saarthi or paste a URL..."
              value={message}
              disabled={loading}
              onChange={(e) =>
                setMessage(e.target.value)
              }
              onKeyDown={handleKeyDown}
            />

            {/* SEND */}

            <button
              className="send-btn"
              onClick={sendMessage}
              disabled={
                loading ||
                (!message.trim() &&
                  !selectedFile)
              }
              type="button"
              title="Send"
            >

              {loading ? (

                <span className="send-loading">
                  ...
                </span>

              ) : (

                <span className="send-icon">
                  ↑
                </span>

              )}

            </button>

          </div>

          <p className="input-hint">
            Enter to send • + for files •
            URL analysis supported • Max 20 MB
          </p>

        </div>

      </div>

      {/* ======================================
          FLOATING STOP READING
      ====================================== */}

      {speakingIndex !== null && (

        <button
          className="floating-stop-reading"
          onClick={stopReading}
          type="button"
        >
          ⏹ Stop Reading
        </button>

      )}

    </div>
  );
}

export default App;