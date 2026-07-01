import React, { useRef, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Send, Cpu, User, FileText, CheckCircle2 } from 'lucide-react';
import { useAppStore } from '../store/appStore';

const ChatInterface = ({ messages, promptInput, setPromptInput, onSendPrompt, isThinking }) => {
  const { setCurrentPage } = useAppStore();
  const chatBottomRef = useRef(null);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  const renderInlineCard = (msg) => {
    switch (msg.cardType) {
      case 'pipeline_result': {
        const data = msg.data;
        return (
          <div className="mt-2 rounded border-2 border-black bg-white p-4 text-xs font-mono">
            <div className="flex items-center justify-between mb-2">
              <span className="font-mono text-[9px] font-bold text-green-700 uppercase tracking-widest bg-green-500/20 px-1.5 py-0.5 border border-green-500/30 rounded">ANALYSIS COMPLETE</span>
              <CheckCircle2 size={14} className="text-green-600" />
            </div>
            <div className="space-y-1 text-black font-medium">
              <div><span className="text-zinc-500">DSN:</span> {data.vsam_dataset.dsn}</div>
              <div><span className="text-zinc-500">Type:</span> {data.vsam_dataset.vsam_type}</div>
              <div><span className="text-zinc-500">Length:</span> {data.vsam_dataset.record_length} bytes</div>
              <div><span className="text-zinc-500">Fields:</span> {data.copybook?.fields.length || 0} fields parsed</div>
              <div><span className="text-zinc-500">Confidence:</span> {(data.vsam_dataset.confidence * 100).toFixed(0)}%</div>
            </div>
            <button
              onClick={() => setCurrentPage('results')}
              className="mt-3 flex w-full items-center justify-center gap-2 border-2 border-black bg-[#00ff4c] px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-wider text-black hover:bg-[#00e676] shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
            >
              <FileText size={12} /> Open Results
            </button>
          </div>
        );
      }
      case 'fields': {
        const { dsn, fields, filename } = msg.data;
        return (
          <div className="mt-2 rounded border-2 border-black bg-[#f4f4f0] p-4 text-[10px] font-mono text-black">
            <div className="font-bold text-[#58a6ff] mb-1">SCHEMA: {dsn}</div>
            <div className="text-[9px] text-zinc-500 mb-2">Copybook: {filename}</div>
            <div className="max-h-40 overflow-y-auto space-y-1">
              {fields.slice(0, 10).map((f, i) => (
                <div key={i} className="flex justify-between border-b border-zinc-200 py-1">
                  <span>Level {f.level} - {f.name}</span>
                  <span className="text-zinc-500">{f.pic || 'Group'} ({f.cobol_type})</span>
                </div>
              ))}
              {fields.length > 10 && (
                <div className="text-[9px] text-center text-[#58a6ff] mt-2 font-bold">
                  ...and {fields.length - 10} more. Open Results page to see all.
                </div>
              )}
            </div>
          </div>
        );
      }
      case 'ops': {
        const { program, operations, key_fields } = msg.data;
        return (
          <div className="mt-2 rounded border-2 border-black bg-[#f4f4f0] p-4 text-[10px] font-mono text-black">
            <div className="font-bold text-black mb-2 uppercase">CRUD OPERATIONS: {program}</div>
            <div className="flex gap-2 flex-wrap mb-3">
              {operations.map((op, i) => (
                <span key={i} className="bg-blue-600/20 text-[#58a6ff] border border-blue-500/30 px-2 py-0.5 rounded text-[9px] font-bold">
                  {op}
                </span>
              ))}
            </div>
            {key_fields.length > 0 && (
              <div>
                <span className="text-zinc-500">Key Fields Used:</span>
                <span className="ml-1 text-purple-700 font-bold">{key_fields.join(', ')}</span>
              </div>
            )}
          </div>
        );
      }
      case 'rules': {
        const { program, rules } = msg.data;
        return (
          <div className="mt-2 rounded border-2 border-black bg-[#f4f4f0] p-4 text-[10px] font-mono text-black">
            <div className="font-bold text-black mb-2 uppercase">BUSINESS RULES: {program}</div>
            <div className="max-h-40 overflow-y-auto space-y-2">
              {rules.map((rule, i) => (
                <div key={i} className="border-b border-zinc-200 pb-2">
                  <div className="text-purple-700 font-bold">{rule.field_name} ({rule.usage})</div>
                  <div className="text-zinc-700 mt-0.5">{rule.description}</div>
                </div>
              ))}
            </div>
          </div>
        );
      }
      case 'vsam': {
        const { dsn, type, length, confidence } = msg.data;
        return (
          <div className="mt-2 rounded border-2 border-black bg-[#f4f4f0] p-4 text-[10px] font-mono text-black">
            <div className="font-bold text-black mb-1 uppercase">VSAM DATASET CANDIDATE</div>
            <div className="space-y-1">
              <div>DSN: <span className="text-[#58a6ff] font-semibold">{dsn}</span></div>
              <div>Type: {type}</div>
              <div>Lrecl: {length} bytes</div>
              <div>Confidence: {(confidence * 100).toFixed(0)}%</div>
            </div>
          </div>
        );
      }
      case 'compare': {
        const { dsn1, dsn2 } = msg.data;
        return (
          <div className="mt-2 rounded border-2 border-black bg-[#f4f4f0] p-3 text-[10px] font-mono text-black">
            <div className="font-bold text-black mb-2 text-center uppercase border-b border-black pb-1">SCHEMA SIDE-BY-SIDE COMPARISON</div>
            <div className="grid grid-cols-2 gap-2">
              <div className="border-r border-black pr-2">
                <span className="text-[#58a6ff] font-bold">{dsn1}</span>
              </div>
              <div className="pl-2">
                <span className="text-[#58a6ff] font-bold">{dsn2}</span>
              </div>
            </div>
          </div>
        );
      }
      default:
        return null;
    }
  };

  return (
    <div className="flex flex-col h-full min-h-[500px] border-2 border-black bg-white shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] rounded overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 border-b-2 border-black bg-white px-4 py-2 shrink-0">
        <Cpu size={14} className="text-black shrink-0" />
        <span className="font-mono text-[10px] font-bold text-black uppercase tracking-wider">mainframeai_copilot / chat</span>
      </div>

      {/* Messages Panel */}
      <div className="flex-1 overflow-y-auto relative bg-[#fafaf8]">
        <div className="min-h-full w-full p-4 space-y-4">
          {messages.map((msg, idx) => {
            const isUser = msg.sender === 'user';
            const isError = msg.type === 'error';
            
            return (
              <div
                key={idx}
                className={`flex items-start gap-2.5 max-w-[85%] ${
                  isUser ? 'ml-auto flex-row-reverse' : 'mr-auto'
                }`}
              >
                {/* Avatar Icon */}
                <div
                  className={`flex h-7 w-7 shrink-0 select-none items-center justify-center rounded-full text-xs font-mono border-2 border-black ${
                    isUser 
                      ? 'bg-black text-[#00ff4c]' 
                      : isError 
                        ? 'bg-red-500 text-white' 
                        : 'bg-zinc-200 text-black'
                  }`}
                >
                  {isUser ? <User size={12} /> : <Cpu size={12} />}
                </div>

                {/* Msg bubbles with solid dropshadows */}
                <div className="flex flex-col">
                  <div
                    className={`rounded border-2 border-black px-3 py-2 text-xs leading-relaxed shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] ${
                      isUser
                        ? 'bg-black text-[#00ff4c]'
                        : isError
                          ? 'bg-red-100 text-red-700'
                          : 'bg-white text-black'
                    }`}
                  >
                    <p className="whitespace-pre-wrap font-sans font-medium">{msg.text}</p>
                    
                    {msg.cardType && renderInlineCard(msg)}
                  </div>
                </div>
              </div>
            );
          })}

          {/* Thinking animation dots */}
          {isThinking && (
            <div className="flex items-start gap-2.5 mr-auto max-w-[85%]">
              <div className="flex h-7 w-7 shrink-0 select-none items-center justify-center rounded-full bg-zinc-200 text-black border-2 border-black">
                <Cpu size={12} />
              </div>
              <div className="rounded border-2 border-black bg-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] px-4 py-2.5 flex gap-1 items-center">
                <span className="h-1.5 w-1.5 animate-bounce bg-black rounded-full [animation-delay:-0.3s]"></span>
                <span className="h-1.5 w-1.5 animate-bounce bg-black rounded-full [animation-delay:-0.15s]"></span>
                <span className="h-1.5 w-1.5 animate-bounce bg-black rounded-full"></span>
              </div>
            </div>
          )}
          <div ref={chatBottomRef} />
        </div>
      </div>

      {/* Input bar */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSendPrompt();
        }}
        className="flex items-center gap-2 border-t-2 border-black p-3 bg-white shrink-0"
      >
        <input
          type="text"
          value={promptInput}
          onChange={(e) => setPromptInput(e.target.value)}
          placeholder="Ask Copilot about mainframe copybooks, schemas, or variables..."
          className="flex-1 rounded border-2 border-black bg-white px-3 py-2 text-xs font-mono text-black focus:border-[#00ff4c] focus:outline-none"
        />
        <button
          type="submit"
          disabled={!promptInput.trim()}
          className="rounded border-2 border-black bg-black p-2 text-[#00ff4c] hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send size={14} />
        </button>
      </form>
    </div>
  );
};

ChatInterface.propTypes = {
  messages: PropTypes.array.isRequired,
  promptInput: PropTypes.string.isRequired,
  setPromptInput: PropTypes.func.isRequired,
  onSendPrompt: PropTypes.func.isRequired,
  isThinking: PropTypes.bool.isRequired,
};

export default ChatInterface;
