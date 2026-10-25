// Op brede schermen staan de details van elke kaart meteen open.
(function () {
  if (window.matchMedia && window.matchMedia("(min-width: 801px)").matches) {
    document.querySelectorAll("details.meer").forEach((blok) => {
      blok.open = true;
    });
  }
})();

// Vergelijking: maximaal drie aanbieders. Het formulier werkt ook zonder dit script.
(function () {
  const vakjes = document.querySelectorAll('input[name="ids"]');
  const teller = document.getElementById("vergelijk-tel");
  const balk = document.getElementById("vergelijk");
  if (!vakjes.length || !teller || !balk) {
    return;
  }

  function gekozen() {
    return Array.from(vakjes).filter((vak) => vak.checked);
  }

  function bijwerken() {
    const aantal = gekozen().length;
    teller.textContent = aantal === 1 ? "1 geselecteerd" : aantal + " geselecteerd";
    balk.classList.toggle("zichtbaar", aantal > 0);
    document.body.classList.toggle("met-balk", aantal > 0);
  }

  vakjes.forEach((vak) => {
    vak.addEventListener("change", () => {
      if (gekozen().length > 3) {
        vak.checked = false;
        teller.textContent = "Maximaal drie aanbieders";
        return;
      }
      bijwerken();
    });
  });

  const formulier = document.querySelector(".zoekform");
  if (formulier) {
    formulier.addEventListener("submit", () => {
      const knop = formulier.querySelector('button[type="submit"]');
      if (knop) {
        knop.textContent = "Zoeken…";
      }
    });
  }

  bijwerken();
})();
