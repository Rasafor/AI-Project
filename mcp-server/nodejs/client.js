import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

// 1. Describe how to launch the server. The transport doesn't connect yet —
//    it just knows the command that will spawn the server as a child
//    process and how to speak to it over stdin/stdout.
const transport = new StdioClientTransport({
  command: "node",
  args: ["server.js"],
});

// 2. Create the client with its own identity. Both sides exchange name +
//    version during the handshake, same as the server did in Step 2 of
//    the server build.
const client = new Client({ name: "notes-demo-client", version: "1.0.0" });

// 3. connect() spawns `node server.js`, opens the stdio pipes, and performs
//    the MCP "initialize" handshake: client sends its protocol version and
//    capabilities, server replies with its own + the name/version we set
//    with McpServer(...). Only after this resolves is the connection live.
await client.connect(transport);
console.log("Connected to:", (await client.getServerVersion()) ?? "notes-server");

// 4. Discover what the server offers, the same three lists the Inspector's
//    tabs show, but here retrieved programmatically.
const { tools } = await client.listTools();
console.log("Tools available:", tools.map((t) => t.name));

const { resources } = await client.listResources();
console.log("Resources available:", resources.map((r) => r.uri));

const { prompts } = await client.listPrompts();
console.log("Prompts available:", prompts.map((p) => p.name));

// 5. Call the tool directly with explicit arguments — this is what a real
//    app does after a model decides to invoke add_note; here we skip the
//    model and call it ourselves to verify the server side works.
const toolResult = await client.callTool({
  name: "add_note",
  arguments: { title: "Client test", content: "Added via the SDK client" },
});
console.log("Tool result:", toolResult.content[0].text);

// 6. Read the resource — expect it to include both the seeded "Welcome"
//    note and the one just added by the tool call above, proving both
//    handlers share the same in-memory store.
const resourceResult = await client.readResource({ uri: "notes://all" });
console.log("Resource contents:", resourceResult.contents[0].text);

// 7. Render the prompt — expect back the templated user message with our
//    raw_text interpolated in, ready to hand to a model.
const promptResult = await client.getPrompt({
  name: "capture_note",
  arguments: { raw_text: "call dentist tues, pick up dry cleaning by fri" },
});
console.log("Prompt messages:", JSON.stringify(promptResult.messages, null, 2));

// 8. Clean shutdown — closes the transport and terminates the child process.
await client.close();
