function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(";").shift();
  return "not found";
}

window.addEventListener("beforeunload", function (e) {
  document.getElementById("content").classList.add("fadeOut");
});

user = {};

fetch("/api/get_user", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ token: getCookie("token") }),
})
  .then((response) => response.json())
  .then((data) => {
    user = data;
    console.log(user);
    document.getElementById("name").innerText = user.name;
  });
