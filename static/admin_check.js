async function checkAccess() {
    const pass = localStorage.getItem("admin_pass");
    if (!pass) { window.location.href = "/login.html"; return; }
    
    const res = await fetch("/api/login", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({password: pass})
    });
    const data = await res.json();
    if (!data.success) { window.location.href = "/login.html"; }
}
checkAccess();
