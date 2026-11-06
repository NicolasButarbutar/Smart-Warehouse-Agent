# SOP Put-Away dan Slotting Barang

## 1. Tujuan dan Peta Zona Rak
Dokumen ini mengatur penentuan lokasi simpan barang setelah Goods Receipt terbit, agar utilisasi rak meningkat dan jarak ambil barang laku cepat berkurang.

Peta Zona Rak. Rak R01 dan R02 untuk elektronik. Rak R03 dan R04 untuk pakaian. Rak R05 dan R06 untuk makanan dan minuman suhu ruang. Rak R07 dan R08 untuk perlengkapan rumah tangga. Rak R09 dan R10 adalah zona fast-moving yang paling dekat dengan jalur pengiriman. Rak R11 dan R12 untuk barang oversize. Rak R13 dan R14 untuk barang fragile. Rak R15 dan R16 adalah cold storage.

## 2. Aturan Slotting dan Rute
Aturan Slotting. Klasifikasi perputaran SKU ditinjau setiap awal bulan berdasarkan jumlah pesanan 30 hari terakhir. SKU kelas cepat ditempatkan di R09 atau R10, kecuali SKU tersebut memerlukan cold storage atau tergolong oversize. Barang berat lebih dari 20 kg disimpan pada level rak paling bawah. Barang yang tidak boleh berdampingan, seperti pangan dan deterjen, wajib dipisah minimal satu rak.

Penentuan Rute. Agen Smart Warehouse menghitung rute dari STAGING menuju rak tujuan memakai algoritma A* dengan bobot jarak pada graf gudang. Operator mengikuti rute pada perangkat genggam. Rute boleh dialihkan bila lorong tertutup, dan operator melaporkan penyimpangan itu melalui tombol "lorong terhalang".

## 3. Pelaksanaan dan Kapasitas
Pelaksanaan Penyimpanan. Operator memindai label koli, berjalan ke lokasi yang disarankan, memindai label rak, lalu mengonfirmasi jumlah. WMS mengubah status stok menjadi "tersedia" setelah kedua pemindaian cocok. Jika rak penuh, operator meminta rekomendasi lokasi alternatif dan dilarang meletakkan barang di lorong.

Batas Kapasitas. Rak dianggap penuh pada okupansi 95 persen. Saat okupansi suatu zona melebihi 85 persen, Supervisor Gudang wajib meninjau SKU slow-moving untuk direlokasi ke rak yang lebih jauh. Target waktu put-away adalah paling lama 4 jam sejak Goods Receipt terbit, dan 30 menit untuk barang beku.

## 4. Tanggung Jawab dan Contoh Penerapan
Supervisor Gudang bertanggung jawab memastikan aturan slotting dijalankan, sedangkan Admin Gudang memperbarui data master seperti dimensi, berat, dan kelas perputaran SKU. Operator tidak boleh mengubah lokasi tanpa pemindaian karena stok akan tampak hilang pada sistem.

Sebagai contoh, smartphone termasuk fragile tetapi perputarannya cepat, sehingga diletakkan pada R09 dengan pelindung tambahan agar dekat dengan jalur kirim. Kulkas bertipe laku cepat tetap disimpan di R12 karena beratnya melebihi 20 kg. Menjelang periode promosi, Kepala Gudang dapat memerintahkan relokasi sementara: SKU promo dipindahkan ke R09 atau R10 maksimal tujuh hari sebelum promo dan dikembalikan paling lambat tujuh hari setelahnya. Setiap relokasi tetap memakai transaksi Pindah di WMS agar riwayat lokasi dapat diaudit. Barang yang lokasinya salah harus dikoreksi pada shift yang sama dan dilaporkan sebagai ketidaksesuaian.
