// Stand-in for an outside AI service that writes order-confirmation messages.
// Mode is read from VENDOR_MODE at call time (default "ok").

function confirmOrder(orderId) {
  const mode = process.env.VENDOR_MODE || 'ok';

  switch (mode) {
    case 'ok':
      return delay(50).then(() => goodMessage(orderId));
    case 'slow':
      return delay(10000).then(() => goodMessage(orderId));
    case 'down':
      return delay(50).then(() => {
        throw new Error('Vendor returned 500 Internal Server Error');
      });
    case 'garbage':
      return delay(50).then(() => garbageMessage(orderId));
    default:
      return Promise.reject(new Error(`Unknown VENDOR_MODE: ${mode}`));
  }
}

function goodMessage(orderId) {
  return `Your order ${orderId} is confirmed and will ship within 2 days.`;
}

// Confidently wrong: either the wrong order number, or a refusal-shaped reply.
function garbageMessage(orderId) {
  const wrongOrderId = Number(orderId) + 1;
  const variants = [
    `Your order ${wrongOrderId} is confirmed and will ship within 2 days.`,
    `As an AI I cannot confirm order ${orderId} at this time.`,
  ];
  return variants[Math.floor(Math.random() * variants.length)];
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

module.exports = { confirmOrder };
