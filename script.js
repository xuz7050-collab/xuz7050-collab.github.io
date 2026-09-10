function toggleMenu() {
  const nav = document.querySelector("nav");

  if (nav.style.display === "flex") {
    nav.style.display = "none";
  } else {
    nav.style.display = "flex";
    nav.style.flexDirection = "column";
    nav.style.position = "absolute";
    nav.style.top = "70px";
    nav.style.right = "20px";
    nav.style.background = "#fff";
    nav.style.padding = "20px";
  }
}

function contactUs() {
  alert("感谢您的咨询！");
}
