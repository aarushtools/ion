$(function() {
    $(".new-feature-close").on("click", function(e) {
        var nf = $(e.target).closest(".new-feature");
        nf.hide("slow");
        $.post("/features/dismiss-announcement/" + nf.data("id"));
    });
});