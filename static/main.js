document.addEventListener("DOMContentLoaded", function () {
    const sujetsDiv = document.getElementById("sujets");
    const form = document.getElementById("formulaire");
    const titreInput = document.getElementById("titre");
  
    function chargerSujets() {
      fetch('/api/sujets')
        .then(res => res.json())
        .then(data => {
          sujetsDiv.innerHTML = '';
          data.forEach(sujet => {
            const p = document.createElement('p');
            p.textContent = sujet.titre;
            sujetsDiv.appendChild(p);
          });
        });
    }
  
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      const titre = titreInput.value.trim();
      if (!titre) return;
  
      fetch('/api/sujets', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ titre })
      })
      .then(res => {
        if (res.ok) {
          titreInput.value = '';
          chargerSujets();
        }
      });
    });
  
    chargerSujets();
  });