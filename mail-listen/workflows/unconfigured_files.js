function main({originMail, data = []}) {
  const mail = JSON.parse(originMail);
  const urls = mail.attachment_urls || [];
  const names = mail.attachments || urls;
  const pdfUrls = [], allImages = [], documentUrls = [];
  urls.forEach((url, index) => {
    const name = String(names[index] || url).split('?')[0].toLowerCase();
    if (name.endsWith('.pdf')) pdfUrls.push(url);
    else if (/\.(png|jpe?g|webp|gif)$/.test(name)) allImages.push(url);
    else documentUrls.push(url);
  });
  for (const item of data || []) {
    if (item && Array.isArray(item.images)) allImages.push(...item.images);
  }
  if (mail.image_url) allImages.push(mail.image_url);
  return {pdfUrls, allImages, documentUrls, mail_text:JSON.stringify(mail)};
}

if (typeof module !== 'undefined') module.exports = {main};
