const installButton = document.querySelector("#install-app");
const installDialog = document.querySelector("#install-dialog");
const instructions = document.querySelector("#install-instructions");
let deferredInstallPrompt;

function setInstructions(content) {
  instructions.replaceChildren(content);
}

function addInstruction(parts) {
  const paragraph = document.createElement("p");
  for (const part of parts) {
    if (typeof part === "string") {
      paragraph.append(document.createTextNode(part));
    } else {
      const emphasis = document.createElement("b");
      emphasis.textContent = part.bold;
      paragraph.append(emphasis);
    }
  }
  return paragraph;
}

function showInstallInstructions() {
  const content = document.createDocumentFragment();
  const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const isSafari = /safari/i.test(navigator.userAgent) && !/crios|fxios|edgios/i.test(navigator.userAgent);

  if (isIos && isSafari && !navigator.standalone) {
    content.append(addInstruction([
      "In Safari, tap the ", { bold: "Share" }, " button, then choose ",
      { bold: "Add to Home Screen" }, " and tap Add."
    ]));
  } else if (isIos && !navigator.standalone) {
    content.append(addInstruction([
      "Open this page in ", { bold: "Safari" },
      " on your iPhone or iPad, tap ", { bold: "Share" },
      ", then choose ", { bold: "Add to Home Screen" }, "."
    ]));
  } else {
    content.append(addInstruction([
      "Use your browser menu and choose ", { bold: "Install app" },
      " or ", { bold: "Add to Home Screen" },
      ". The exact wording depends on your browser."
    ]));
  }

  setInstructions(content);
  if (!installDialog.open) installDialog.showModal();
}

installButton.addEventListener("click", async () => {
  if (!deferredInstallPrompt) {
    showInstallInstructions();
    return;
  }

  deferredInstallPrompt.prompt();
  const { outcome } = await deferredInstallPrompt.userChoice;
  deferredInstallPrompt = null;
  if (outcome === "accepted") {
    installButton.textContent = "App installed";
    installButton.disabled = true;
  }
});

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
});

window.addEventListener("appinstalled", () => {
  installButton.textContent = "App installed";
  installButton.disabled = true;
});

if ("serviceWorker" in navigator && window.location.protocol === "https:") {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./service-worker.js").catch((error) => {
      console.error("Could not register the Democracydot offline experience.", error);
    });
  });
}
