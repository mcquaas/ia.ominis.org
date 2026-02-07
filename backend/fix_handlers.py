#!/usr/bin/env python3
"""Add source validation to handlers in rag_api.py"""

with open("/home/ubuntu/rag_api.py", "r") as f:
    content = f.read()

# Find and replace the streaming handler to add validation
old_code = '''                    elif etype == "done":
                        # Use tracked answer if done.answer is empty (streaming mode)
                        if not event.get("answer"):
                            event["answer"] = full_answer
                        if not event.get("sources") and final_sources:
                            event["sources"] = final_sources

                    event_json = json.dumps(event, ensure_ascii=False)'''

new_code = '''                    elif etype == "done":
                        # Use tracked answer if done.answer is empty (streaming mode)
                        if not event.get("answer"):
                            event["answer"] = full_answer
                        if not event.get("sources") and final_sources:
                            event["sources"] = final_sources
                        # Validate external sources before sending
                        if event.get("sources"):
                            event["sources"] = filter_valid_sources(event["sources"], validate=True)

                    event_json = json.dumps(event, ensure_ascii=False)'''

if old_code in content:
    content = content.replace(old_code, new_code)
    print("Streaming handler updated")
else:
    print("Warning: Could not find streaming handler code")

# Also add validation for non-streaming
old_nonstream = '''            response = {
                "answer": full_answer.strip(),
                "sources": final_sources[:5],'''

new_nonstream = '''            # Validate sources before returning
            final_sources = filter_valid_sources(final_sources, validate=True)
            response = {
                "answer": full_answer.strip(),
                "sources": final_sources[:5],'''

if old_nonstream in content:
    content = content.replace(old_nonstream, new_nonstream)
    print("Non-streaming handler updated")
else:
    print("Warning: Could not find non-streaming handler code")

with open("/home/ubuntu/rag_api.py", "w") as f:
    f.write(content)

print("Handler validation fix applied")
