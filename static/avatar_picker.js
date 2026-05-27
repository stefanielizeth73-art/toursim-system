(function () {
    function fileName(input) {
        return input.files && input.files[0] ? input.files[0].name : "";
    }

    document.addEventListener("change", function (event) {
        const target = event.target;
        const picker = target.closest("[data-avatar-picker]");
        if (!picker) {
            return;
        }

        const preview = picker.querySelector("[data-avatar-preview]");
        if (target.type === "radio") {
            picker.querySelectorAll("[data-avatar-choice]").forEach(function (choice) {
                choice.classList.toggle("is-selected", choice.contains(target));
            });
            if (preview) {
                preview.src = "/static/" + target.value;
            }
            return;
        }

        if (target.type === "file") {
            const upload = picker.querySelector("[data-avatar-upload]");
            const label = picker.querySelector("[data-avatar-file-name]");
            const selectedName = fileName(target);
            if (upload) {
                upload.classList.toggle("has-file", Boolean(selectedName));
            }
            if (label) {
                label.textContent = selectedName || "支持 jpg / png / webp / gif / svg";
            }
            if (preview && target.files && target.files[0]) {
                preview.src = URL.createObjectURL(target.files[0]);
            }
        }
    });
}());
