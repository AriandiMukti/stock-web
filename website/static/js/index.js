function deleteNote(noteId){
    fetch("/delete-note", {
        method: "POST",
        body: JSON.stringify({ noteId: noteId }),
    }).then((_res) => {
        window.location.href = "/";
    });
}

/*
function modifiedPortfolio(id, param){
  var stockName = document.getElementById(id).value;
  var param = param;
  fetch("/portfolio", {
    method: "POST",
    body: JSON.stringify({ stockName: stockName,
    param: param }),
  }).then((_res) => {
      window.location.href = "/portfolio";
  });
  
}
*/

let slideIndex = 1;
// Guarded: with the dynamic-chart rebuild there are no .mySlides elements
// on any current page, so calling this unconditionally used to throw
// (slides[0] was undefined) and kill the rest of this script — which is
// why daterangepicker() below never ran. Kept here in case a slideshow
// view is reintroduced later.
if (document.getElementsByClassName("mySlides").length > 0) {
    showSlides(slideIndex);
}

// Next/previous controls


function plusSlides(n) {
  showSlides(slideIndex += n);    
}

// Thumbnail image controls
function currentSlide(n) {
  showSlides(slideIndex = n);
}



function showSlides(n) {
  let i;
  let slides = document.getElementsByClassName("mySlides");
  if (slides.length === 0) { return; }
  if (n > slides.length) {slideIndex = 1}
  if (n < 1) {slideIndex = slides.length}
  for (i = 0; i < slides.length; i++) {
    slides[i].style.display = "none";
  }

  slides[slideIndex-1].style.display = "block";


}




$("#alert").fadeTo(1000, 1).slideUp(300, function(){
$("#alert").slideUp(300);
}); 


$(function() {
  $('input[name="rangeDate"]').daterangepicker({
    opens: 'left'
  });
});
  

/*
function hideAndShow(id, id2) {
  var x = document.getElementById(id);
  var x2 = document.getElementById(id2);
  if (x.style.display === "none") {
    x.style.display = "block";
  } else {
    x.style.display = "none";
  }

  if (x2.style.display === "block") {
    x2.style.display = "none";
  }
}



         
        


document.onkeydown = previewOnKey;

function previewOnKey(e) {
 // left key
  if (e.keyCode == 37) {
      var previousImg = document.getElementsByClassName("mySlides").previousElementSibling;
      if (previousImg) {
          preview(previousImg);
      }
  }

  // right key
  if (e.keyCode == 39) {
      var nextImg = document.getElementById("mySlides").nextElementSibling;
      if (nextImg) {
          preview(nextImg);
      }
  }
}
*/