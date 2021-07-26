/**
 * Implements the [[Faq]] component
 * @packageDocumentation
 */
import React from 'react';
import { Row, Col, Table, Collapse } from 'antd';
import { Link } from 'react-router-dom';
import * as Data from './FaqData.js';

import './Faq.less';

/**
 * The [[Faq]] component is just a static FAQ page
 * @class
 */
export class Faq extends React.Component<void> {
  render(): React.ReactNode {
    const { Panel } = Collapse;
    return (
      <div className="faq">
        <Row className="primary-row">
          <Col span={24}>
            <span className="page-title">Frequently Asked Questions</span>
          </Col>
        </Row>

        <Collapse bordered={false}>
          <Panel header="What is Go?" key="1">
            <p style={{ paddingLeft: 24 }}>
              Go is the official URL shortener of Rutgers University.
            </p>
          </Panel>
          <Panel header="Who has access to Go?" key="2">
            <p style={{ paddingLeft: 24 }}>
              All current Rutgers University faculty and staff members are able
              to log into <a href="https://go.rutgers.edu/">go.rutgers.edu</a>{' '}
              using their NetID and password. Undergraduate student workers can
              be granted access to Go by a faculty or staff member.
            </p>
          </Panel>
          <Panel
            header="Can I choose the URL my link will be shortened to?"
            key="3"
          >
            <p style={{ paddingLeft: 24 }}>
              To create a custom short URL, you must have the &ldquo;power
              user&rdquo; role. This role is available only to faculty and staff
              members. To request to be added to this role, please email&nbsp;
              <a href="mailto:oss@oss.rutgers.edu">oss@oss.rutgers.edu</a>.
            </p>
          </Panel>
          <Panel
            header="How can I grant an undergraduate student worker access to Go?"
            key="4"
          >
            <p style={{ paddingLeft: 24 }}>
              To grant access to an undergraduate user, click the&nbsp;
              <Link to="/roles/whitelisted">Whitelist </Link>
              tab in the navigation bar, then enter the user&rsquo;s NetID and
              the reason the user needs access to Go. Undergraduate users should
              only use Go for purposes related to their employment with the
              University.
            </p>
          </Panel>
          <Panel
            header="Why would I create multiple aliases for one link?"
            key="5"
          >
            <p style={{ paddingLeft: 24 }}>
              One use of multiple aliases would be creating distinct aliases for
              Twitter and Facebook if you wish to track the number of
              impressions from each platform.
            </p>
          </Panel>
          <Panel header="What is the organizations feature?" key="6">
            <p style={{ paddingLeft: 24 }}>
              The organizations feature is a collaborative tool that allows a
              group of users to view each other&rsquo;s links. For example,
              users working together on a project may want to be able to see
              each other&rsquo;s links.
            </p>
          </Panel>
          <Panel header="How can I use the organizations feature?" key="7">
            <p style={{ paddingLeft: 24 }}>
              Only faculty and staff members are able to create a new
              organization. To do so, navigate to the{' '}
              <Link to="/orgs">Organizations </Link>
              page and click the &ldquo;Create an Organization&rdquo; button.
              You will automatically be made an administrator of the newly
              created organization. Once the organization has been created, you
              may navigate to its management page and use the &ldquo;Add a
              Member&rdquo; button to add members to the organization. Only
              admins of the organization can delete an organization which
              removes member access to the shared links.
            </p>
            <p style={{ paddingLeft: 24 }}>
              To view the links created by members of an organization, click the
              &ldquo;Filter Links&rdquo; dropdown next to the search bar, and
              select the organization whose links you would like to view.
            </p>
          </Panel>
          <Panel header="Why can I view this link but not edit it?" key="8">
            <p style={{ paddingLeft: 24 }}>
              As a viewer, you can see a link&apos;s stats and QR code; however,
              you cannot edit it. You can request for edit access by hitting the
              mail icon next to the link which will send a request to the owner
              of the link.
            </p>
          </Panel>
          <Panel header="How do I share my links?" key="9">
            <p style={{ paddingLeft: 24 }}>
              To share your link with a specific user or an organization, you
              must either be the owner or an editor of the link. Click on the
              &ldquo;manage sharing&rdquo; icon to the right of your link and
              add the user&apos;s NetId or organization name. You can also
              specify whether you want them to be a viewer or editor of the
              link.{' '}
            </p>
          </Panel>
          <Panel
            header="What access does somone have when I make them a viewer or editor?"
            key="10"
          >
            <Table
              size="small"
              pagination={{ pageSize: 25, hideOnSinglePage: true }}
              dataSource={Data.data}
              columns={Data.cols}
            />
          </Panel>
        </Collapse>
      </div>
    );
  }
}
