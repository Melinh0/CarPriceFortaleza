(function () {
  const campoMarca = document.getElementById("campo-marca");
  const campoModelo = document.getElementById("campo-modelo");
  if (!campoMarca || !campoModelo || typeof MARCAS === "undefined") return;

  function opcao(valor, texto) {
    const el = document.createElement("option");
    el.value = valor;
    el.textContent = texto;
    return el;
  }

  function popularModelos() {
    const marca = campoMarca.value;
    const atual = campoModelo.value;
    campoModelo.innerHTML = "";
    campoModelo.appendChild(opcao("", "Todos os modelos"));

    let modelos = [];
    if (marca) {
      const encontrada = MARCAS.find((m) => m.nome === marca);
      modelos = encontrada ? encontrada.modelos : [];
    } else {
      MARCAS.forEach((m) => m.modelos.forEach((mod) => modelos.push(mod)));
    }
    modelos.sort((a, b) => a.localeCompare(b, "pt-BR"));
    modelos.forEach((mod) => campoModelo.appendChild(opcao(mod, mod)));

    if (modelos.includes(atual)) campoModelo.value = atual;
  }

  campoMarca.addEventListener("change", popularModelos);
  popularModelos();
})();
