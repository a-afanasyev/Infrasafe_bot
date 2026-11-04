-- Удалить демо-заявки, созданные записью видео (житель 920000001, текст «Засор в ванной…»).
begin;
create temp table demo as
  select r.request_number from requests r join users u on u.id = r.user_id
  where u.telegram_id = 920000001 and (r.description like 'Засор в ванной%' or r.description like 'Vannada tiqilib%')
    and r.created_at > now() - interval '1 day';
select * from demo;
delete from notifications where request_number_fk in (select request_number from demo);
delete from ratings where request_number in (select request_number from demo);
delete from request_assignments where request_number in (select request_number from demo);
delete from request_comments where request_number in (select request_number from demo);
delete from shift_assignments where request_number in (select request_number from demo);
delete from requests where request_number in (select request_number from demo);
commit;
