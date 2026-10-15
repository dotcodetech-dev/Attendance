/**
 * Print only the mess receipt on an 80mm thermal roll.
 *
 * window.print() prints the whole document, and hiding the app with
 * `visibility` still leaves its layout height behind — that's what caused
 * blank pages after each token. Instead we clone the receipt into a
 * print-only root directly under <body>; @media print CSS hides the app
 * (#root, display:none → zero height) and shows just this clone, so each
 * job is exactly one receipt long.
 */
export function printReceipt(): void {
  const receipt = document.getElementById("mess-receipt");
  if (!receipt) return;

  let printRoot = document.getElementById("print-root");
  if (!printRoot) {
    printRoot = document.createElement("div");
    printRoot.id = "print-root";
    document.body.appendChild(printRoot);
  }
  printRoot.innerHTML = "";
  const clone = receipt.cloneNode(true) as HTMLElement;
  clone.removeAttribute("id"); // avoid duplicate id while both exist
  printRoot.appendChild(clone);

  window.print();

  // Clear after the job is handed to the spooler (kiosk-printing returns fast;
  // with a dialog, print() blocks until it closes, so this runs after either way).
  window.setTimeout(() => {
    const root = document.getElementById("print-root");
    if (root) root.innerHTML = "";
  }, 500);
}
